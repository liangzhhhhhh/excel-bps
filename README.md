# Excel BPS · CPA BPS 整合包

为已有的 CPA + Manager 部署安装 BPS 插件和配套管理面板，适用于 TEAM 使用场景。

- 项目仓库：[liangzhhhhhh/excel-bps](https://github.com/liangzhhhhhh/excel-bps)
- 问题反馈：[Issues](https://github.com/liangzhhhhhh/excel-bps/issues)
- 当前随包版本：`0.5.31`
- 运行平台：`Linux AMD64 / glibc`

本仓库提供预编译插件、管理面板和安装脚本，不包含 Go / TypeScript 业务源码。安装无需 Go 或 Node.js，也没有授权码校验；使用 BPS 账号仍需完成 OAuth 授权。

> 这是现有服务的安装与升级包。请先准备正常运行的 Docker Compose CPA 和 Manager，再按以下步骤操作。Windows、ARM64 和 musl / Alpine CPA 镜像不在此包的支持范围内。

## 1. 仓库内容

```text
.
├── README.md
├── cpa-bps-unified-0.5.31-linux-amd64-binary.zip
└── cpa-bps-unified-0.5.31-linux-amd64-binary/
    ├── install.sh                    # 统一安装入口
    ├── BINARY.json                   # 文件清单与 SHA256 校验值
    ├── plugin/
    │   ├── dist/                    # 插件、配置工具与加载检查工具
    │   ├── scripts/                 # 插件安装与兼容性检查脚本
    │   └── notices/                 # 第三方许可证
    └── panel/
        ├── apps/web/dist/           # 预编译管理面板
        ├── scripts/                 # 面板升级脚本
        ├── Dockerfile.bps-panel
        └── LICENSE
```

仓库同时包含解压目录和 ZIP，选择一种使用即可。下文默认使用 Git 克隆得到的解压目录。

## 2. 安装前准备

### 2.1 环境要求

| 项目 | 要求 |
| --- | --- |
| 服务器 | Linux x86_64，使用 root 权限安装 |
| CPA 镜像 | `linux/amd64`，基于 glibc，能通过随包插件加载检查 |
| Python | Python 3.9 或以上 |
| Docker | 已启动，支持 BuildKit 构建 |
| Compose | 支持 `docker compose` 命令 |
| 基础工具 | `sh`、`sha256sum`；Git 下载需要 `git`，ZIP 解压需要 `unzip` |
| 现有服务 | CPA 与 Manager 已通过 Docker Compose 部署并正常运行 |
| 配置与数据 | CPA 配置使用文件绑定挂载，Manager 持久化挂载 `/data` |

安装器还会检查以下条件：

- CPA 的 `/CLIProxyAPI/config.yaml` 必须绑定到宿主机真实配置文件，不支持用符号链接代替。
- 如已挂载 `/CLIProxyAPI/plugins`，它必须是可写的宿主机绑定目录，且不能是符号链接。
- 容器的 Compose 标签必须指向服务器上仍然存在的 Compose 文件。
- 宿主机 `/etc/localtime` 必须是可读取的有效时区文件。

没有现成 Manager 时，可以显式选择仅安装插件；本仓库不提供从空服务器部署基础 CPA / Manager 的流程。

### 2.2 检查服务器和容器

通过 SSH 登录实际运行 CPA 的 Linux 服务器。以下安装命令在该服务器上执行，不是在本地 Windows 终端执行。

```sh
# 切换到 root；已经是 root 时跳过
sudo -i

uname -m
python3 --version
docker version
docker compose version
command -v sh sha256sum

# 记录实际 CPA 和 Manager 容器名称
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
```

`uname -m` 应显示 `x86_64`，Python 应至少为 3.9。容器应正常运行；若当前服务已在重启或报错，先修复基础部署。

可进一步查看实际挂载，下面的名称需要替换为上一步查到的容器名：

```sh
docker inspect CPA容器名 --format '{{json .Mounts}}'
docker inspect Manager容器名 --format '{{json .Mounts}}'
```

确认 CPA 配置的挂载目标是 `/CLIProxyAPI/config.yaml`，Manager 存在 `/data` 挂载。安装前自行备份 Compose 文件、CPA 配置及 Manager 持久化数据。安装器的回滚备份不能替代完整数据备份。

## 3. 获取安装包

### 方式一：克隆当前仓库

```sh
git clone https://github.com/liangzhhhhhh/excel-bps.git
cd excel-bps/cpa-bps-unified-0.5.31-linux-amd64-binary
```

### 方式二：上传 ZIP 后解压

从[当前仓库](https://github.com/liangzhhhhhh/excel-bps)获取 `cpa-bps-unified-0.5.31-linux-amd64-binary.zip`，上传到服务器后执行：

```sh
mkdir -p /opt/excel-bps
unzip cpa-bps-unified-0.5.31-linux-amd64-binary.zip -d /opt/excel-bps
cd /opt/excel-bps/cpa-bps-unified-0.5.31-linux-amd64-binary
```

执行前确保当前目录包含 `install.sh`、`BINARY.json`、`plugin/` 和 `panel/`：

```sh
ls -l install.sh BINARY.json plugin panel
```

安装入口会自动校验 `BINARY.json` 中列出的文件。不要改动包内文件后直接安装，否则会因校验失败停止。当前仓库未提供独立的 ZIP `.sha256` 文件，因此无需执行针对不存在校验文件的命令。SHA256 用于检查完整性，不是发行者数字签名。

## 4. 安装插件和面板

安装会重建 CPA 和 Manager 容器，带来短暂中断，建议在维护时段执行，并先在测试环境验证。

### 4.1 单套部署：自动识别

在安装包目录内执行：

```sh
sh install.sh
```

默认按运行中容器的 Compose **服务名标签**查找 `cli-proxy-api` 和 `cpa-manager-plus`。它们不是必须照抄的容器名称；只有各找到一个匹配服务时，自动识别才会成功。

### 4.2 多套部署或自定义服务：指定容器

先用 `docker ps` 找出目标容器，再替换下面示例中的名称：

```sh
sh install.sh \
  --cpa-container cpamp-cli-proxy-api-1 \
  --manager-container cpamp-cpa-manager-plus-1
```

两项参数分别指定本次要更新的 CPA 和 Manager。多套部署时，应选择相互配套的两个容器。

### 4.3 仅安装插件

明确不需要更新 Manager 面板时使用：

```sh
sh install.sh --plugin-only --cpa-container cpamp-cli-proxy-api-1
```

这种方式跳过面板安装。现有面板是否提供 BPS 专用授权和管理功能，取决于其版本；首次使用建议采用默认的插件与面板一同安装方式。即使选择仅安装插件，也应保留完整安装包，因为文件校验仍会检查包内清单。

### 4.4 安装器执行的操作

1. 校验安装包文件、容器信息、Compose 文件及挂载条件。
2. 使用现有 CPA 镜像启动隔离检查容器，验证插件动态库能否加载。
3. 生成新配置，备份旧配置及已有插件文件，再安装插件和宿主机时区文件。
4. 生成 Compose override，以原 CPA 镜像重建 CPA 服务。
5. 基于原 Manager 镜像构建包含新面板 HTML 的镜像，再更新 Manager 服务。
6. 检查容器状态、镜像与挂载，输出安装结果及回滚命令。

原 Compose 文件不会被直接改写；后续部署依赖生成的 override。CPA 保留当前镜像，Manager 以当前镜像为基础添加面板，已有持久化挂载会被保留并核对。

> 插件和面板分步更新。如果面板阶段失败，插件可能已经更新成功。应根据报错修复后重跑统一安装入口，或分别按对应结果文件回滚。

## 5. 登录面板并授权 BPS

### 5.1 打开 Manager

1. 使用原有 Manager 访问地址和端口，本教程不假定固定端口。
2. 按 `Ctrl + F5` 强制刷新页面，以加载新面板。
3. 使用 **Manager 管理员密钥**登录。

Manager 管理员密钥和 CPA Management Key 用途不同：前者用于登录面板，后者用于 Manager 连接 CPA。若 Manager 尚未初始化，按页面向导填写管理员密钥、Manager 能访问的 CPA 地址和 CPA Management Key。管理员密钥仅在 Manager 首次启动日志中输出一次，优先使用部署时保存的值。

### 5.2 检查插件状态

1. 进入 **插件管理 → 已安装**，查找 BPS / `cpa-bps`。
2. 检查插件全局开关和 BPS 插件启用状态。全局开关关闭时，单个插件启用也不会生效。
3. 如需调整参数，打开 **编辑配置**，按当前版本实际显示的字段填写并保存。

插件配置字段由插件动态提供，不需要为本教程额外编造或添加 YAML 字段。保持默认值完成首次授权与验收后，再按需要调整。

### 5.3 完成账号 OAuth 授权

1. 从 **插件管理** 中 BPS 的 **OAuth 登录** 操作进入插件授权页面。
2. 按插件页面提示打开授权入口，登录有使用权限的 BPS 账号并完成授权。
3. 如页面要求提交回调地址，按页面提示提交浏览器实际返回的完整地址；不要自行拼接或修改其中的参数。
4. 等待页面确认授权完成，再进入 **凭证管理** 检查是否出现 `cpa-bps` 凭证。

不要在通用「OAuth 登录」页面寻找固定的 BPS 卡片，本包通过 BPS 插件页面提供专用授权入口。插件内的实际按钮名称与步骤以页面显示为准。

### 5.4 查看额度与并发

打开 BPS 凭证详情，可以查看：

- **BPS 套餐与额度**：套餐、剩余额度、重置时间及可用重置卡数量；「刷新信息」主动查询状态，不发送生成请求。
- **BPS 账号并发**：当前处理数、排队数和已设上限；调整并发上限后点击保存，`0` 表示不限。
- **使用重置卡**：需要页面确认，会消耗卡片且无法撤销，具体效果由上游决定。

若提示某个 BPS 账号凭证失效，应重新授权该账号，无需因此退出并重新登录整个管理面板。

## 6. 安装后验收

### 6.1 检查服务与结果文件

在安装包目录执行：

```sh
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
cat BPS-INSTALL-RESULT.txt
cat panel/BPS-PANEL-INSTALL-RESULT.txt
```

仅安装插件时，不会生成本次面板安装结果。确认目标容器正常运行、没有持续重启，再完成以下功能检查：

1. Manager 可以登录，CPA 连接正常。
2. 插件管理能看到 BPS，且启用状态正确。
3. BPS OAuth 授权完成，凭证可见。
4. 凭证详情能刷新套餐或额度信息。
5. 用现有客户端选择当前 CPA 实际提供的 BPS 模型，发送一次最小测试请求，并检查请求监控与响应。

模型名称、API 地址和客户端密钥以现有部署为准，本包不预设一组适用于所有部署的值。容器运行正常和动态库检查通过，只代表基础检查通过，不能替代真实授权和请求验收。

### 6.2 查看日志

将示例容器名称替换为自己的名称：

```sh
docker logs --tail 100 cpamp-cli-proxy-api-1
docker logs --tail 100 cpamp-cpa-manager-plus-1
```

## 7. 后续维护和回滚

### 7.1 保留安装产物

安装成功后，请保留：

- 包目录内的 `BPS-INSTALL-RESULT.txt`。
- 包目录内的 `panel/BPS-PANEL-INSTALL-RESULT.txt`。
- CPA 第一个 Compose 文件所在目录下的 `bps-backup-*` 目录。
- Manager Compose 文件旁的 `compose.bps-panel-*.json` 和 `compose.bps-panel-rollback-*.json`。

这些文件包含备份、实际使用的 override 以及回滚信息。后续重建服务时，应使用结果文件记录的完整 Compose 命令前缀，并带上对应 override；只运行原 Compose 文件可能丢失插件挂载或新面板设置。

### 7.2 回滚 CPA 插件

优先复制 `BPS-INSTALL-RESULT.txt` 中记录的真实回滚命令。其形式为：

```sh
sh /实际的Compose目录/bps-backup-实际后缀/rollback.sh
```

上面的路径是占位示例，不能原样执行。回滚脚本恢复旧配置及原有插件文件，再重建 CPA。插件安装阶段的部分失败会自动触发回滚；若安装中途退出，应查看终端输出中的备份位置与回滚结果。

### 7.3 回滚 Manager 面板

打开 `panel/BPS-PANEL-INSTALL-RESULT.txt`，执行其中记录的完整回滚命令。它使用生成的回滚 override 恢复安装前 Manager 镜像及面板路径设置。

插件和面板需要分别回滚；恢复其中一项不会自动恢复另一项。回滚会重建相应服务，可能造成短暂中断。

### 7.4 同步服务器时区

安装后若更改了宿主机时区，在包目录执行：

```sh
sh install.sh --sync-timezone --cpa-container cpamp-cli-proxy-api-1
```

此操作要求已有可写的插件绑定挂载，只同步时区文件，不重建或重启服务，下一次请求开始使用同步后的时区。

## 8. 常见问题

| 现象或错误 | 处理方法 |
| --- | --- |
| `Cannot select exactly one...` | 未找到唯一的默认 Compose 服务；用 `docker ps` 确认容器，再显式传入 `--cpa-container` 和 `--manager-container`。 |
| `Existing Docker Compose metadata/files are required` | 检查是否使用 Docker Compose 部署，以及标签记录的原 Compose 文件是否仍存在；裸 `docker run` 部署不满足此安装器前提。 |
| `Binary bundle integrity check failed` | 文件缺失或内容与清单不符；重新获取完整包，不要跳过校验。 |
| 提示 CPA 配置或插件挂载不符合要求 | 检查 `/CLIProxyAPI/config.yaml` 是否为真实文件绑定挂载，现有插件目录是否为可写绑定挂载。 |
| Manager 缺少 `/data` 挂载 | 先为现有 Manager 正确配置持久化并验证；明确只需插件时再使用 `--plugin-only`。 |
| 动态库加载失败 | 检查 CPA 镜像架构与 glibc 兼容性；本包不支持 ARM64 或 musl / Alpine CPA 镜像。 |
| 插件已安装，但面板更新失败 | 查看面板构建或容器检查报错，修复后重跑 `sh install.sh`；需要恢复时分别执行插件和面板回滚。 |
| 页面仍然是旧界面 | 使用 `Ctrl + F5` 刷新，并确认访问的是本次更新的 Manager。 |
| 通用 OAuth 页面没有 BPS | 从「插件管理」中 BPS 的 OAuth 操作进入专用授权页面。 |
| BPS 凭证失效 | 重新授权该 BPS 账号，再刷新凭证状态。 |
| 后续重建后插件或面板消失 | 核对是否遗漏安装结果文件记录的 Compose override。 |

查看统一入口支持的参数：

```sh
sh install.sh --help
```

需要单独检查插件能否在现有 CPA 镜像中加载时，可在包目录执行：

```sh
sh plugin/scripts/check-library.sh cpamp-cli-proxy-api-1
```

此检查会运行临时隔离容器，不等同于实际 CPA 插件注册、账号授权或业务请求成功。

## 9. 项目说明

本仓库的下载、使用说明和反馈入口统一为 [liangzhhhhhh/excel-bps](https://github.com/liangzhhhhhh/excel-bps)。提交问题时请附包版本、服务器架构、脱敏后的错误信息和相关容器状态，不要公开管理员密钥、API Key、OAuth 回调参数或账号凭证。

第三方组件的许可条款保留在安装包的 `plugin/notices/` 与 `panel/LICENSE` 中。使用、修改或分发时，请遵守各组件适用的许可证及相关分发要求。
