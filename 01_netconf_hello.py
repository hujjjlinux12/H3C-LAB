"""第一课：连接一台华三交换机，观察 NETCONF 握手。"""

import argparse
from getpass import getpass

from ncclient import manager


def main():
    parser = argparse.ArgumentParser(description="查看华三设备的 NETCONF 会话和能力")
    parser.add_argument("host", help="设备管理地址")
    parser.add_argument("username", help="有 NETCONF 登录权限的账号")
    parser.add_argument("--port", type=int, default=830, help="NETCONF SSH 端口，默认 830")
    args = parser.parse_args()

    password = getpass("NETCONF 登录密码：")
    # connect 建立 SSH 会话、请求 netconf 子系统，并交换 <hello>。
    with manager.connect(
        host=args.host,
        port=args.port,
        username=args.username,
        password=password,
        device_params={"name": "h3c"},
        hostkey_verify=True,
        allow_agent=False,
        look_for_keys=False,
        timeout=10,
        manager_params={"timeout": 10},
    ) as session:
        print(f"NETCONF session-id = {session.session_id}")
        for capability in sorted(session.server_capabilities):
            print(capability)
    # 离开 with 时，ncclient 关闭 NETCONF 会话。


if __name__ == "__main__":
    main()
