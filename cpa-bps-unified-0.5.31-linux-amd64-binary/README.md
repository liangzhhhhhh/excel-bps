# BPS 0.5.31 二进制整合包

包含 Linux AMD64/glibc 插件与配套面板；不包含 Go/TypeScript 业务源码。
无授权码校验。BPS 账号 OAuth 授权仍需在安装后完成。

适用于已有 Docker Compose CPA + Manager 的 Linux AMD64/glibc 服务器。
需要 root、Python 3.9+、Docker BuildKit、Docker Compose、sh、sha256sum；无需 Go/Node。
不是空服务器一键部署，也不支持 Windows、ARM64 或 musl/Alpine CPA 镜像。

先用随包 ZIP 的 .sha256 文件执行 sha256sum -c，再解压运行 sh install.sh。
多套部署可指定 --cpa-container 容器名 --manager-container 容器名。
安装入口默认同时更新插件与面板，会短暂重启两个服务。
安装前校验文件哈希，并在现有 CPA 镜像的隔离容器中验证 .so 加载。
保留 CPA/Manager 后端镜像及数据；面板只复制预编译 HTML 到现有镜像。
请先在暂存环境验收。插件与面板不是原子升级：面板失败时插件可能已更新。
回滚命令见 BPS-INSTALL-RESULT.txt 和 panel/BPS-PANEL-INSTALL-RESULT.txt，
插件失败备份见安装输出的 bps-backup-* 目录。保留这些文件和 Compose override。

SHA256 用于检查文件完整性，不是发行者数字签名；从可信渠道获取 ZIP 与校验值。
前端 JavaScript 和安装脚本可阅读，二进制可逆向，不代表防破解。
保留随包第三方许可证，并履行适用的源码提供等分发义务。
