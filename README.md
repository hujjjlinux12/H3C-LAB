# 华三设备自动化开发实验

先用一台华三交换机做出一个只读接口查询工具。第一条路径走 NETCONF，第二条路径用该设备的 Comware RESTful API 查询同一份数据。有了两个实机回包，再抽取公共逻辑。

## 开发路线

| 阶段 | 要写的代码 | 验收结果 |
| --- | --- | --- |
| 1. NETCONF 握手（本课） | `01_netconf_hello.py` | 打印会话 ID 和设备声明的能力 |
| 2. 读一个接口 | 构造 `<get>` 过滤器，解析 XML | 取管理口或任意已知端口的名称与状态，并用 CLI 核对 |
| 3. 用 RESTful 读取同一个接口 | 用 HTTPS 建立认证会话并发送 GET，解析 JSON | 得到与 NETCONF 一致的字段值 |
| 4. 做成小工具 | 统一输出字段，再加入设备清单和报告 | 选择接入方式，得到相同格式的接口记录 |

## 对照项目 · H3C `pycw7-ansible`

华三在 GitHub 上公开了这套面向 Comware 7 的 Ansible 模块和 Python 库，采用 Apache 2.0 许可。我们用它对照 NETCONF 的连接、查询和解析。实验脚本直接用 `ncclient`，之后用华三的开发指南实现 RESTful 这一条接入路径。 [源码仓库](https://github.com/H3C/pycw7-ansible) · [许可](https://github.com/H3C/pycw7-ansible/blob/main/LICENSE)

| 按这个顺序读源码 | 跟我们的实验对照 |
| --- | --- |
| [`COM7.open()`](https://github.com/H3C/pycw7-ansible/blob/main/pycw7/comware.py#L58-L108) 把地址、认证和超时交给 `ncclient.manager.connect()` | 第一课也用 `device_params={"name": "h3c"}`。在我们的脚本里，`with` 管理会话生命周期，主机指纹校验默认开启。 |
| [`Facts._get_interface_list()`](https://github.com/H3C/pycw7-ansible/blob/main/pycw7/features/facts.py#L54-L73) 生成 `Ifmgr → Interfaces → Interface → Name` 的子树，调用 `get`，再从 XML 提取名称 | 第二课先沿着这条路径读接口名，再按名称匹配一个接口。 |
| [`Interface._get_iface_index()`](https://github.com/H3C/pycw7-ansible/blob/main/pycw7/features/interface.py#L145-L167) 以接口名为匹配条件，从回包提取 `IfIndex` | 用 `Name` 和 `IfIndex` 作为第一组对照字段。接口状态等字段用实际型号的回包确认后再加。 |
| [`comware_facts.py`](https://github.com/H3C/pycw7-ansible/blob/main/library/comware_facts.py#L86-L125) 负责参数、打开连接、调用采集和返回结果 | 等查询能跑通后，再把我们的命令入口与查询、解析逻辑拆开。 |

**读源码练习**。对比 `Name()` 和 `Name(self.interface_name)` 生成的 XML。前者用空节点选择返回字段，后者带具体文本用作匹配条件。然后打开华三的 RESTful 指南，找 `Ifmgr/Interfaces` 的 `select-fields` 和 `filter-condition` 示例，看看同样的选择和匹配在 HTTP 请求里如何表达。 [华三 NETCONF API 开发指南](https://www.h3c.com/cn/Service/Document_Software/Document_Center/Home/Switches/00-Public/Developer_Guides/Development_Guide/H3C_NETCONF_API-Long/?CHID=735012) · [华三 RESTful 开发指南](https://www.h3c.com/cn/Service/Document_Software/Document_Center/Home/Switches/00-Public/Developer_Guides/Development_Guide/H3C_Comware_RESTful-22387/?CHID=1079924)

## 第一课 · 先建立 NETCONF 会话

旧脚本用 `invoke_shell()` 打开终端，发 `display` 命令并等待文本回显。现在 SSH 仍负责连接和认证，客户端请求的是 `netconf` 子系统。建立会话时双方交换 XML `<hello>`。设备的 `<hello>` 包含会话 ID 和能力列表，`ncclient` 会替我们处理握手和报文边界。

### 1. 在华三设备上看型号和服务状态

在已有的设备 CLI 执行下面两个查看命令。记下型号、Comware Release，以及 `NETCONF over SSH` 的状态和端口。

```text
display version
display netconf service
```

华三部分交换机的命令参考列出默认端口 `830`。如果设备提示命令不存在，或 NETCONF 处于 `Disabled`，先查对应型号和 Release 的配置指南。启用服务、VTY/AAA 设置和账号权限都属于设备侧配置，本课脚本只连接已开通的实验设备。 [华三 S5130S-HI-G / S5130S-EI-G 命令参考](https://www.h3c.com/en/d_202409/2262090_294551_0.htm)

### 2. 在 Windows 上确认能连到该端口

把例子里的 `192.0.2.10` 换成设备管理地址，`lab-user` 换成有 NETCONF 权限的实验账号。实际端口以设备回显为准。

```powershell
Test-NetConnection 192.0.2.10 -Port 830
ssh -p 830 -s lab-user@192.0.2.10 netconf
```

第一次连接时，用可信来源核对设备的 SSH 主机指纹，再接受并写入 `known_hosts`。看到 `<hello>` 后，按 `Ctrl+C` 结束这次手动连接，或关闭专门用来测试的终端。Python 使用同一设备地址、端口和 Windows 用户，以便找到同一条主机密钥记录。

### 3. 用 Python 重做同一次连接

在 `h3c-lab` 目录运行。已有虚拟环境时可以跳过创建环境的命令。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -X utf8 -m pip install --progress-bar off -r requirements.txt
.\.venv\Scripts\python.exe 01_netconf_hello.py 192.0.2.10 lab-user
```

打开 `01_netconf_hello.py`，沿着三步读代码。先从终端接收参数和密码，再用 `manager.connect()` 建立会话，最后遍历 `session.server_capabilities`。`with` 负责退出时关闭会话。`timeout` 用在连接上，`manager_params` 中的 `timeout` 用在 NETCONF RPC 上。 [ncclient Manager 文档](https://github.com/ncclient/ncclient/blob/master/docs/source/manager.rst)

**动手练习**。先运行脚本，再自己加一行，输出服务器声明了多少项能力。观察是否有 `urn:ietf:params:netconf:base:1.0` 或 `urn:ietf:params:netconf:base:1.1`。看到 `session-id` 和能力列表，就完成了第一课。

如果 TCP 不通，检查实验网络、设备端口和管理访问控制。如果 SSH 能建立但 NETCONF 子系统请求被拒绝，检查设备的 NETCONF 服务以及账号是否获准使用该服务。如果主机指纹校验失败，先核对管理地址、端口和设备指纹。

## 下一课怎么衔接

我们会选一个已知接口做对照。NETCONF 侧从型号对应的 API 文档确认 XML 命名空间和过滤器。RESTful 侧从同一型号的文档确认 HTTPS 端口、认证和路径。华三交换机的开发指南给出的接口资源示例是 `GET /api/v1/Ifmgr/Interfaces`。这是 Comware 的 RESTful API 路径，不能据此假定设备提供标准 RESTCONF 的 `/restconf/data`。 [Comware RESTful 二次开发指南](https://www.h3c.com/cn/Service/Document_Software/Document_Center/Home/Switches/00-Public/Developer_Guides/Development_Guide/H3C_Comware_RESTful-22387/?CHID=1079924)
