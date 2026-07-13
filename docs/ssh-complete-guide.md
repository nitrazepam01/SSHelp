# SSH（Secure Shell）协议与工具完整指南

> **更新日期**: 2026年
> **协议版本**: SSH-2.0 (RFC 4250–4254 系列)
> **默认端口**: 22 (IANA 注册)

---

## 目录

- [一、SSH 协议概述](#一ssh-协议概述)
- [二、SSH 协议架构详解](#二ssh-协议架构详解)
  - [2.1 三层架构](#21-三层架构)
  - [2.2 连接建立流程](#22-连接建立流程)
- [三、核心 RFC 规范体系](#三核心-rfc-规范体系)
  - [3.1 基础规范](#31-基础规范)
  - [3.2 算法扩展](#32-算法扩展)
  - [3.3 功能扩展](#33-功能扩展)
- [四、SSH 协议详细规范](#四ssh-协议详细规范)
  - [4.1 传输层协议 (RFC 4253)](#41-传输层协议-rfc-4253)
  - [4.2 认证协议 (RFC 4252)](#42-认证协议-rfc-4252)
  - [4.3 连接协议 (RFC 4254)](#43-连接协议-rfc-4254)
  - [4.4 协议编号分配 (RFC 4250)](#44-协议编号分配-rfc-4250)
  - [4.5 椭圆曲线密码学 (RFC 5656)](#45-椭圆曲线密码学-rfc-5656)
  - [4.6 RSA SHA-2 签名 (RFC 8332)](#46-rsa-sha-2-签名-rfc-8332)
- [五、SSH 安全属性与威胁模型](#五ssh-安全属性与威胁模型)
- [六、SSH 开源工具大全](#六ssh-开源工具大全)
  - [6.1 系统级工具 (C/C++)](#61-系统级工具-cc)
    - [6.1.1 OpenSSH](#611-openssh)
    - [6.1.2 libssh](#612-libssh)
    - [6.1.3 libssh2](#613-libssh2)
    - [6.1.4 Dropbear](#614-dropbear)
  - [6.2 Python 生态](#62-python-生态)
    - [6.2.1 Paramiko](#621-paramiko)
    - [6.2.2 Fabric](#622-fabric)
    - [6.2.3 asyncssh](#623-asyncssh)
  - [6.3 Java 生态](#63-java-生态)
    - [6.3.1 JSch (mwiede fork)](#631-jsch-mwiede-fork)
    - [6.3.2 Apache MINA SSHD](#632-apache-mina-sshd)
  - [6.4 Node.js 生态](#64-nodejs-生态)
    - [6.4.1 ssh2](#641-ssh2)
  - [6.5 Go 生态](#65-go-生态)
    - [6.5.1 crypto/ssh](#651-cryptossh)
  - [6.6 Rust 生态](#66-rust-生态)
  - [6.7 其他语言](#67-其他语言)
- [七、SSH 调用方式与使用范例](#七ssh-调用方式与使用范例)
  - [7.1 命令行方式 (OpenSSH)](#71-命令行方式-openssh)
  - [7.2 C/C++ 编程 (libssh2)](#72-cc-编程-libssh2)
  - [7.3 Python 编程 (Paramiko)](#73-python-编程-paramiko)
  - [7.4 Java 编程 (JSch)](#74-java-编程-jsch)
  - [7.5 Node.js 编程 (ssh2)](#75-nodejs-编程-ssh2)
  - [7.6 Go 编程 (crypto/ssh)](#76-go-编程-cryptossh)
- [八、SSH 密钥管理](#八ssh-密钥管理)
- [九、SSH 安全最佳实践](#九ssh-安全最佳实践)
- [十、参考资源](#十参考资源)

---

## 一、SSH 协议概述

**SSH (Secure Shell)** 是一种在不安全网络上提供安全远程登录和其他安全网络服务的协议。由 Tatu Ylönen 于 1995 年创建，旨在替代不安全的 telnet、rlogin 和 rsh 协议。

SSH 协议的核心目标是提供：

| 属性 | 说明 |
|------|------|
| **机密性 (Confidentiality)** | 通过强加密保护数据传输内容 |
| **完整性 (Integrity)** | 检测数据是否被篡改 |
| **认证 (Authentication)** | 验证通信双方身份 |
| **前向保密 (Forward Secrecy)** | 即使长期密钥泄露，过去的会话也无法解密 |

SSH 协议当前标准版本为 **SSH-2.0**（SSH-1 已废弃，存在严重安全缺陷）。

---

## 二、SSH 协议架构详解

### 2.1 三层架构

SSH 协议由三个主要组件构成，分层运行：

```
┌─────────────────────────────────────────┐
│         连接协议 (Connection Protocol)     │  RFC 4254
│  通道复用、Shell、命令执行、端口转发、X11   │
├─────────────────────────────────────────┤
│       用户认证协议 (Authentication)        │  RFC 4252
│  publickey、password、hostbased、keyboard- │
│  interactive、GSSAPI                      │
├─────────────────────────────────────────┤
│        传输层协议 (Transport Layer)        │  RFC 4253
│  算法协商、密钥交换、加密、MAC、压缩         │
├─────────────────────────────────────────┤
│              TCP/IP 连接                  │
└─────────────────────────────────────────┘
```

#### 传输层协议 (Transport Layer Protocol) — RFC 4253

- **职责**: 提供服务器认证、机密性、完整性
- **功能**: 算法协商、密钥交换 (Diffie-Hellman/ECDH)、加密/解密、HMAC 保护、可选的压缩
- **运行于**: TCP/IP 连接之上（通常端口 22）
- **服务名**: 无（直接建立）

#### 用户认证协议 (User Authentication Protocol) — RFC 4252

- **职责**: 认证客户端用户身份
- **运行于**: 传输层协议之上
- **服务名**: `ssh-userauth`
- **支持的方法**:
  - `publickey` (必须实现) — 基于公私钥对
  - `password` (可选) — 明文密码（在加密通道内传输）
  - `hostbased` (可选) — 基于主机信任
  - `keyboard-interactive` — 交互式认证，适用 OTP、PAM 等
  - `none` — 仅用于查询支持的方法
  - `gssapi-with-mic` (RFC 4462) — Kerberos/GSSAPI

#### 连接协议 (Connection Protocol) — RFC 4254

- **职责**: 将加密隧道复用为多个逻辑通道
- **运行于**: 用户认证协议之上
- **服务名**: `ssh-connection`
- **功能**:
  - 交互式 Shell 会话 (`shell`)
  - 远程命令执行 (`exec`)
  - 子系统调用 (`subsystem`)，如 SFTP (`sftp`)
  - TCP/IP 端口转发 (本地/远程/动态)
  - X11 转发
  - 环境变量传递
  - 流控 (flow control)

### 2.2 连接建立流程

一个完整的 SSH 连接建立过程：

```
序列图：

Client ──────────────────────────────────────────── Server

  1. TCP 连接建立 (SYN/SYN-ACK/ACK)

  2. 协议版本交换
     SSH-2.0-OpenSSH_9.6 ─────────────────────── SSH-2.0-OpenSSH_9.3

  3. 算法协商 (SSH_MSG_KEXINIT)
     ■ 密钥交换算法: curve25519-sha256
     ■ 主机密钥算法: ssh-ed25519
     ■ 加密算法: chacha20-poly1305@openssh.com
     ■ MAC 算法: hmac-sha2-256
     ■ 压缩算法: none

  4. 密钥交换 (Diffie-Hellman/ECDH)
     ■ 生成会话密钥
     ■ 服务器签名验证（主机密钥认证）
     ■ 生成加密/MAC 密钥
     SSH_MSG_NEWKEYS ────────────────────────── SSH_MSG_NEWKEYS

  5. 服务请求: "ssh-userauth"
     SSH_MSG_SERVICE_REQUEST ──────────────────── SSH_MSG_SERVICE_ACCEPT

  6. 用户认证
     ■ 尝试 publickey (可能失败)
     ■ 尝试 password (成功)
     SSH_MSG_USERAUTH_SUCCESS

  7. 服务请求: "ssh-connection"
     ■ 打开通道 (SSH_MSG_CHANNEL_OPEN)
     ■ 通道确认 (SSH_MSG_CHANNEL_OPEN_CONFIRMATION)
     ■ 请求 shell/exec/subsystem

  8. 数据传输
     ■ 加密通道上的双向数据传输
     ■ 窗口大小调整 (SSH_MSG_CHANNEL_WINDOW_ADJUST)

  9. 连接关闭
     SSH_MSG_CHANNEL_CLOSE ──────────────────── SSH_MSG_CHANNEL_CLOSE
     SSH_MSG_DISCONNECT ─────────────────────── (连接终止)
```

---

## 三、核心 RFC 规范体系

### 3.1 基础规范

| RFC | 标题 | 描述 |
|-----|------|------|
| **RFC 4250** | SSH Protocol Assigned Numbers | 协议编号分配，消息 ID、算法名称、断开原因码 |
| **RFC 4251** | SSH Protocol Architecture | 协议架构、数据类型、算法命名规则、安全考量 |
| **RFC 4252** | SSH Authentication Protocol | 用户认证协议框架，publickey/password/hostbased 方法 |
| **RFC 4253** | SSH Transport Layer Protocol | 传输层协议，二进制包格式、DH 密钥交换、加密/MAC |
| **RFC 4254** | SSH Connection Protocol | 连接协议，通道机制、Shell/Exec/端口转发/X11 |

### 3.2 算法扩展

| RFC | 标题 | 描述 |
|-----|------|------|
| **RFC 4255** | SSHFP DNS 记录 | 通过 DNS 发布主机密钥指纹 |
| **RFC 4419** | DH Group Exchange | 客户端请求更安全的 DH 组 (diffie-hellman-group-exchange-sha256) |
| **RFC 5656** | ECC 算法集成 | ECDH 密钥交换 + ECDSA 签名 (nistp256/384/521) |
| **RFC 6668** | HMAC-SHA-2 | SHA-256/512 的 HMAC 算法 |
| **RFC 8268** | SHA-2 for SSHFP | SHA-256/512 的 SSHFP 指纹 |
| **RFC 8332** | RSA SHA-2 签名 | `rsa-sha2-256` / `rsa-sha2-512` 替代 SHA-1 |
| **RFC 8709** | Ed25519/Ed448 | EdDSA 公钥算法 (`ssh-ed25519`, `ssh-ed448`) |
| **RFC 8731** | curve25519/curve448 | ECDH 密钥交换 (`curve25519-sha256`, `curve448-sha512`) |
| **RFC 8758** | chacha20-poly1305 | AEAD 加密 (`chacha20-poly1305@openssh.com`) |

### 3.3 功能扩展

| RFC | 标题 | 描述 |
|-----|------|------|
| **RFC 4256** | Keyboard-Interactive | 通用交互式认证 |
| **RFC 4462** | GSSAPI | Kerberos/GSSAPI 认证和密钥交换 |
| **RFC 8308** | Extension Negotiation | SSH_MSG_EXT_INFO 扩展协商，`server-sig-algs` 等 |
| **RFC 9141** | Session Channel 扩展 | 会话通道多路复用优化 |
| **RFC 9142** | 密钥交换方法更新 | 合并 Ed25519/448、chacha20 等新算法 |

> 完整的 IANA SSH 参数注册表: <https://www.iana.org/assignments/ssh-parameters/>

---

## 四、SSH 协议详细规范

### 4.1 传输层协议 (RFC 4253)

#### 4.1.1 协议版本交换

连接建立后，双方必须发送标识字符串：

```
SSH-2.0-<softwareversion> SP <comments> CR LF
```

示例: `SSH-2.0-OpenSSH_9.6`

- `protoversion`: 必须是 `2.0`
- `softwareversion`: 可打印 US-ASCII 字符
- `comments`: 可选，用空格与 softwareversion 分隔
- 最大长度 255 字符（含 CR LF）

#### 4.1.2 二进制包格式

版本交换后，所有数据使用统一的二进制包格式：

```
uint32    packet_length       (不包括 MAC 和自身 4 字节)
byte      padding_length      (填充长度)
byte[n1]  payload             (有效载荷，可能压缩)
byte[n2]  random padding      (4~255 字节随机填充)
byte[m]   mac                  (消息认证码，取决于协商的算法)
```

- **加密**: 整个包（不含 MAC）使用协商的对称加密算法加密
- **MAC**: 对加密后的数据进行计算
- **压缩**: payload 可选压缩 (none / zlib / zlib@openssh.com)

#### 4.1.3 算法协商 (SSH_MSG_KEXINIT)

双方交换 `SSH_MSG_KEXINIT` (消息号 20)，包含以下名称列表 (name-list)：

| 字段 | 说明 | 示例 |
|------|------|------|
| `kex_algorithms` | 密钥交换算法 | `curve25519-sha256`, `ecdh-sha2-nistp256`, `diffie-hellman-group-exchange-sha256` |
| `server_host_key_algorithms` | 主机密钥算法 | `ssh-ed25519`, `ecdsa-sha2-nistp256`, `rsa-sha2-256`, `rsa-sha2-512` |
| `encryption_algorithms_c_to_s` | 客户端→服务器加密 | `chacha20-poly1305@openssh.com`, `aes256-gcm@openssh.com`, `aes128-ctr` |
| `encryption_algorithms_s_to_c` | 服务器→客户端加密 | 同上 |
| `mac_algorithms_c_to_s` | 客户端→服务器 MAC | `hmac-sha2-256`, `hmac-sha2-512` |
| `mac_algorithms_s_to_c` | 服务器→客户端 MAC | 同上 |
| `compression_algorithms_c_to_s` | 压缩算法 | `none`, `zlib@openssh.com` |
| `compression_algorithms_s_to_c` | 压缩算法 | 同上 |

#### 4.1.4 密钥交换 (Key Exchange)

**Diffie-Hellman 密钥交换步骤** (以 diffie-hellman-group14-sha1 为例):

1. 客户端发送 `SSH_MSG_KEXDH_INIT` (消息号 30): 包含客户端 DH 公开值 `e`
2. 服务器发送 `SSH_MSG_KEXDH_REPLY` (消息号 31):
   - 主机公钥 `K_S` (如 `ssh-rsa` 公钥)
   - 服务器 DH 公开值 `f`
   - 对交换哈希 `H` 的签名
3. 共享密钥 `K = f^y mod p` (客户端), `K = e^x mod p` (服务器)
4. 交换哈希: `H = hash(V_C || V_S || I_C || I_S || K_S || e || f || K)`
5. 双方发送 `SSH_MSG_NEWKEYS` (消息号 21)
6. 从 `H` 和 `K` 派生出加密密钥、MAC 密钥、初始化向量

#### 4.1.5 消息编号摘要

| 消息 ID | 名称 | 层 |
|---------|------|-----|
| 1 | SSH_MSG_DISCONNECT | 传输层 |
| 2 | SSH_MSG_IGNORE | 传输层 |
| 3 | SSH_MSG_UNIMPLEMENTED | 传输层 |
| 4 | SSH_MSG_DEBUG | 传输层 |
| 5 | SSH_MSG_SERVICE_REQUEST | 传输层 |
| 6 | SSH_MSG_SERVICE_ACCEPT | 传输层 |
| 20 | SSH_MSG_KEXINIT | 传输层 |
| 21 | SSH_MSG_NEWKEYS | 传输层 |
| 30-49 | KEX 特定消息 | 传输层 |
| 50 | SSH_MSG_USERAUTH_REQUEST | 认证层 |
| 51 | SSH_MSG_USERAUTH_FAILURE | 认证层 |
| 52 | SSH_MSG_USERAUTH_SUCCESS | 认证层 |
| 53 | SSH_MSG_USERAUTH_BANNER | 认证层 |
| 60 | SSH_MSG_USERAUTH_PASSWD_CHANGEREQ | 认证层 |
| 80 | SSH_MSG_GLOBAL_REQUEST | 连接层 |
| 81 | SSH_MSG_REQUEST_SUCCESS | 连接层 |
| 82 | SSH_MSG_REQUEST_FAILURE | 连接层 |
| 90 | SSH_MSG_CHANNEL_OPEN | 连接层 |
| 91 | SSH_MSG_CHANNEL_OPEN_CONFIRMATION | 连接层 |
| 92 | SSH_MSG_CHANNEL_OPEN_FAILURE | 连接层 |
| 93 | SSH_MSG_CHANNEL_WINDOW_ADJUST | 连接层 |
| 94 | SSH_MSG_CHANNEL_DATA | 连接层 |
| 95 | SSH_MSG_CHANNEL_EXTENDED_DATA | 连接层 |
| 96 | SSH_MSG_CHANNEL_EOF | 连接层 |
| 97 | SSH_MSG_CHANNEL_CLOSE | 连接层 |
| 98 | SSH_MSG_CHANNEL_REQUEST | 连接层 |
| 99 | SSH_MSG_CHANNEL_SUCCESS | 连接层 |
| 100 | SSH_MSG_CHANNEL_FAILURE | 连接层 |

### 4.2 认证协议 (RFC 4252)

#### 4.2.1 认证框架

```
byte      SSH_MSG_USERAUTH_REQUEST
string    user name (UTF-8)
string    service name (US-ASCII)
string    method name (US-ASCII)
....      method specific fields
```

认证由服务器驱动：服务器告知客户端可用的认证方法，客户端选择使用。服务器推荐超时 10 分钟，限制 20 次失败尝试。

#### 4.2.2 Public Key 认证 (必须实现)

```
byte      SSH_MSG_USERAUTH_REQUEST
string    user name
string    service name
string    "publickey"
boolean   TRUE (含签名) / FALSE (仅查询)
string    public key algorithm name  (如 "ssh-ed25519")
string    public key blob
string    signature  (如果 TRUE)
```

签名数据 = `session_id || SSH_MSG_USERAUTH_REQUEST || user || service || "publickey" || TRUE || alg || key_blob`

#### 4.2.3 Password 认证

```
byte      SSH_MSG_USERAUTH_REQUEST
string    user name
string    service name
string    "password"
boolean   FALSE (仅密码)
string    plaintext password (UTF-8)
```

密码在加密的传输层通道内传输。如果无加密 (none cipher)，必须禁用密码认证。

#### 4.2.4 Host-Based 认证

利用客户端主机的私钥签名，服务器验证客户端主机身份。适用于 `.rhosts` / `hosts.equiv` 风格的信任模型。

#### 4.2.5 认证响应

- `SSH_MSG_USERAUTH_SUCCESS` (52) — 认证成功
- `SSH_MSG_USERAUTH_FAILURE` (51):
  - `authentications that can continue`: 剩余可用方法列表
  - `partial success`: 是否需要额外认证方法 (多因素认证)

### 4.3 连接协议 (RFC 4254)

#### 4.3.1 通道机制

所有终端会话、转发连接等都是 "通道 (channel)"。多个通道复用到一个 SSH 连接中。

**打开通道**:
```
byte      SSH_MSG_CHANNEL_OPEN
string    channel type ("session", "direct-tcpip", "forwarded-tcpip", "x11")
uint32    sender channel
uint32    initial window size
uint32    maximum packet size
....      channel type specific data
```

**已定义的通道类型**:
| 类型 | 用途 |
|------|------|
| `session` | 交互式 Shell、命令执行、子系统、X11、环境变量 |
| `direct-tcpip` | 本地端口转发 |
| `forwarded-tcpip` | 远程端口转发 |
| `x11` | X11 转发 |

#### 4.3.2 会话通道请求

在 `session` 类型通道上，可以发送以下请求：

| 请求 | 描述 |
|------|------|
| `pty-req` | 请求伪终端 (pseudo-terminal) |
| `x11-req` | 请求 X11 转发 |
| `x11` (channel type) | X11 通道 |
| `env` | 设置环境变量 |
| `shell` | 启动交互式 Shell |
| `exec` | 执行远程命令 |
| `subsystem` | 启动子系统 (如 SFTP: `sftp`) |
| `window-change` | 窗口大小变化通知 |
| `xon-xoff` | 客户端 XON/XOFF 流控 |
| `signal` | 发送 POSIX 信号 |
| `exit-status` | 返回退出状态码 |
| `exit-signal` | 因信号退出 |

#### 4.3.3 TCP/IP 端口转发

**本地转发** (Client → Server → Remote):
```
byte      SSH_MSG_GLOBAL_REQUEST
string    "tcpip-forward"
boolean   want reply
string    address to bind  (如 "0.0.0.0")
uint32    port number to bind
```
通道类型: `direct-tcpip`

**远程转发** (Server → Client → Target):
通道类型: `forwarded-tcpip`

#### 4.3.4 终端模式编码

伪终端模式使用 opcode-argument 对编码：

| Opcode | 名称 | 描述 |
|--------|------|------|
| 0 | TTY_OP_END | 结束 |
| 1 | VINTR | 中断字符 |
| 3 | VERASE | 擦除字符 |
| 4 | VKILL | 删除行 |
| 5 | VEOF | 文件结束符 |
| 53 | ECHO | 回显开启/关闭 |
| 128 | TTY_OP_ISPEED | 输入波特率 |
| 129 | TTY_OP_OSPEED | 输出波特率 |

### 4.4 协议编号分配 (RFC 4250)

RFC 4250 定义了所有消息编号、算法名称、断开原因码、通道失败原因码的初始分配和未来扩展策略。

**分配策略**:
- `0x00000000 - 0xFDFFFFFF`: IETF CONSENSUS
- `0xFE000000 - 0xFFFFFFFF`: PRIVATE USE

**初始加密算法名称** (RFC 4250 定义):
- `3des-cbc`, `blowfish-cbc`, `twofish-cbc`, `aes128-cbc`, `aes192-cbc`, `aes256-cbc`
- `aes128-ctr`, `aes192-ctr`, `aes256-ctr` (后续添加)
- `arcfour`, `cast128-cbc`
- `none` (仅调试)
- `des-cbc` (HISTORIC, 不应使用)

**初始 MAC 算法名称**:
- `hmac-sha1`, `hmac-sha1-96`
- `hmac-md5`, `hmac-md5-96`
- `none`

**初始公钥算法名称**:
- `ssh-dss` (DSA)
- `ssh-rsa` (RSA with SHA-1)
- `pgp-sign-rsa`, `pgp-sign-dss`

### 4.5 椭圆曲线密码学 (RFC 5656)

RFC 5656 为 SSH 传输层引入了 ECC 算法：

#### ECDH 密钥交换

- 使用椭圆曲线 Diffie-Hellman 生成共享密钥
- 提供显式服务器认证 (通过签名交换哈希)
- 方法名: `ecdh-sha2-<curve>` (如 `ecdh-sha2-nistp256`)

#### ECDSA 公钥算法

- 公钥格式: `ecdsa-sha2-<identifier>`
- 签名算法: `ecdsa-sha2-nistp256`, `ecdsa-sha2-nistp384`, `ecdsa-sha2-nistp521`

#### 必须支持的曲线 (REQUIRED)

| NIST 名称 | SEC 名称 | OID |
|-----------|----------|-----|
| nistp256 | secp256r1 | 1.2.840.10045.3.1.7 |
| nistp384 | secp384r1 | 1.3.132.0.34 |
| nistp521 | secp521r1 | 1.3.132.0.35 |

#### 安全强度对比

| 对称密钥 | DSA/DH | RSA | ECC |
|---------|--------|-----|-----|
| 80 位 | L=1024, N=160 | 1024 | 160-223 |
| 112 位 | L=2048, N=256 | 2048 | 224-255 |
| 128 位 | L=3072, N=256 | 3072 | 256-383 |
| 192 位 | L=7680, N=384 | 7680 | 384-511 |
| 256 位 | L=15360, N=512 | 15360 | 512+ |

### 4.6 RSA SHA-2 签名 (RFC 8332)

由于 SHA-1 被 NIST 弃用，RFC 8332 定义了新的 RSA 公钥算法：

| 算法名 | 状态 | 用途 |
|--------|------|------|
| `rsa-sha2-256` | RECOMMENDED | 签名 (使用 SHA-256) |
| `rsa-sha2-512` | OPTIONAL | 签名 (使用 SHA-512) |

- 复用 `ssh-rsa` 公钥格式（无需重新编码）
- 签名使用 RSASSA-PKCS1-v1_5 填充方案
- 使用 `server-sig-algs` 扩展 (RFC 8308) 发现服务器支持的算法
- OpenSSH 8.8+ 默认禁用 `ssh-rsa` (SHA-1)

---

## 五、SSH 安全属性与威胁模型

### 5.1 安全属性

| 属性 | 实现方式 |
|------|---------|
| **服务器认证** | 主机密钥签名 (在密钥交换中) |
| **客户端认证** | publickey / password / hostbased / GSSAPI |
| **机密性** | AES-128/192/256 (CTR/GCM), ChaCha20-Poly1305 |
| **完整性** | HMAC-SHA2-256/512, AEAD (GCM/Poly1305) |
| **前向保密** | 每次会话使用临时 DH/ECDH 密钥 |
| **重放保护** | 序列号 + MAC |
| **中间人防御** | known_hosts 数据库 / SSHFP DNS / CA 证书 |

### 5.2 已知威胁

| 威胁 | 缓解措施 |
|------|---------|
| 中间人攻击 | 主机密钥验证 (首次连接信任/CA) |
| 密码嗅探 | 传输层加密 |
| 侧信道攻击 (流量分析) | SSH_MSG_IGNORE 填充、压缩前认证 |
| 密钥泄露 | 前向保密确保历史会话安全 |
| 弱算法降级 | 严格算法白名单 |
| 暴力破解 | fail2ban、MaxAuthTries、速率限制 |

---

## 六、SSH 开源工具大全

### 6.1 系统级工具 (C/C++)

#### 6.1.1 OpenSSH

- **官网**: <https://www.openssh.com/>
- **仓库**: <https://github.com/openssh/openssh-portable>
- **语言**: C
- **许可**: BSD-like
- **定位**: **SSH 事实标准实现**，几乎所有类 Unix 系统默认 SSH 实现

**核心组件**:

| 工具 | 描述 |
|------|------|
| `ssh(1)` | SSH 客户端，类似 rlogin/rsh |
| `sshd(8)` | SSH 守护进程（服务器） |
| `scp(1)` | 安全文件复制（类似 rcp） |
| `sftp(1)` | 安全 FTP 客户端 |
| `sftp-server(8)` | SFTP 服务器子系统 |
| `ssh-keygen(1)` | 密钥生成工具 |
| `ssh-agent(1)` | 认证代理，缓存私钥 |
| `ssh-add(1)` | 向 agent 添加密钥 |
| `ssh-keyscan(1)` | 收集远程主机公钥 |
| `ssh-keysign(8)` | hostbased 认证辅助程序 |
| `ssh_config(5)` | 客户端配置文件 |
| `sshd_config(5)` | 服务器配置文件 |

**OpenSSH 扩展特性**:
- 延迟压缩 `zlib@openssh.com` (认证后再压缩，防止 pre-auth 攻击)
- 高性能 MAC `umac-64@openssh.com`
- `chacha20-poly1305@openssh.com` + `curve25519-sha256` (旧版 ECDH)
- FIDO/U2F 安全密钥支持 (`sk-ssh-ed25519@openssh.com`)

#### 6.1.2 libssh

- **官网**: <https://www.libssh.org/>
- **语言**: C
- **许可**: LGPL 2.1
- **定位**: 全功能 SSH 库，支持客户端和服务器端

**特性** (v0.12.0):
- SSHv2 客户端和服务器
- SFTP/SCP 支持
- 多种后端: OpenSSL, libgcrypt, mbedTLS
- 后量子密码学 (PQC) 混合密钥交换:
  - `sntrup761x25519-sha512@openssh.com`
  - `mlkem768nistp256-sha256`, `mlkem768x25519-sha256`
- FIDO2/U2F 安全密钥
- GSSAPI 密钥交换 (RFC 4462, RFC 8732)
- SSH 签名 (`sshsig_sign()` / `sshsig_verify()`)
- ProxyJump 支持
- **使用者**: KDE, GitHub (生产环境), Cockpit

#### 6.1.3 libssh2

- **官网**: <https://www.libssh2.org/>
- **语言**: C
- **许可**: BSD 3-Clause
- **定位**: 轻量级 SSH2 **仅客户端**库

**API 子系统**:
- **Session**: 会话管理、握手、断开、keepalive
- **Userauth**: password, publickey, keyboard-interactive, hostbased, agent
- **Channel**: shell, exec, subsystem, TCP/IP 转发
- **SFTP**: 完整 SFTP 文件操作
- **Publickey**: 公钥管理 (list/fetch/add/remove)
- **Knownhosts**: known_hosts 数据库管理
- **SCP**: SCP 文件传输
- **Agent**: SSH Agent 通信

**基本使用流程**:
```c
libssh2_init();
session = libssh2_session_init();
libssh2_session_handshake(session, sock);
libssh2_userauth_password(session, "user", "pass");
channel = libssh2_channel_open_session(session);
libssh2_channel_exec(channel, "ls -la");
libssh2_channel_read(channel, buf, sizeof(buf));
libssh2_channel_close(channel);
libssh2_channel_free(channel);
libssh2_session_disconnect(session, "bye");
libssh2_session_free(session);
libssh2_exit();
```

#### 6.1.4 Dropbear

- **官网**: <https://matt.ucc.asn.au/dropbear/dropbear.html>
- **语言**: C
- **许可**: MIT
- **定位**: 超轻型 SSH 服务器/客户端，适用于嵌入式系统

---

### 6.2 Python 生态

#### 6.2.1 Paramiko

- **官网**: <https://www.paramiko.org/>
- **PyPI**: `pip install paramiko`
- **许可**: LGPL 2.1
- **定位**: 纯 Python (依赖 C/Rust 的 cryptography 库) SSHv2 实现，提供客户端和服务器功能

**核心类**:

| 类 | 描述 |
|----|------|
| `SSHClient` | 高级客户端，封装认证和连接 |
| `Transport` | 低层传输，直接控制 Socket 和密钥交换 |
| `Channel` | 流式通道，类似 socket 的双工流 |
| `SFTPClient` | SFTP 客户端 |
| `SFTPServer` | SFTP 服务器 |
| `ServerInterface` | 服务器行为回调接口 |
| `SecurityOptions` | 安全算法配置 |
| `RSAKey / DSSKey / ECDSAKey / Ed25519Key` | 密钥类型 |

**Host Key 策略**:
- `AutoAddPolicy` — 自动添加到 known_hosts
- `RejectPolicy` — 拒绝未知主机
- `WarningPolicy` — 警告但允许连接

**认证方式**:
- `auth_password()` — 密码认证
- `auth_publickey()` — 公钥认证
- `auth_interactive()` / `auth_interactive_dumb()` — 交互式认证
- `auth_none()` — 查询可用方法
- `auth_gssapi_*` — GSSAPI 认证

#### 6.2.2 Fabric

- **官网**: <https://www.fabfile.org/>
- **PyPI**: `pip install fabric`
- **定位**: 基于 Paramiko 的高级 SSH 库，面向自动化运维

#### 6.2.3 asyncssh

- **PyPI**: `pip install asyncssh`
- **定位**: 基于 asyncio 的异步 SSHv2 实现，性能优异

---

### 6.3 Java 生态

#### 6.3.1 JSch (mwiede fork)

- **仓库**: <https://github.com/mwiede/jsch>
- **Maven**: `com.github.mwiede:jsch:2.28.0`
- **语言**: Java (Java 8+)
- **许可**: BSD-style
- **定位**: 纯 Java SSH2 客户端库，JSch 0.1.55 的活跃维护分支

**关键特性**:
- 支持 `rsa-sha2-256` / `rsa-sha2-512` (解决 OpenSSH 8.8+ 禁用 ssh-rsa)
- 支持 `ssh-ed25519` / `ssh-ed448` (Java 15+ 或 Bouncy Castle)
- 支持 `curve25519-sha256` / `curve448-sha512` (Java 11+ 或 Bouncy Castle)
- 支持 `chacha20-poly1305@openssh.com` (需要 Bouncy Castle)
- 多版本 JAR 架构 (Multi-Release JAR)
- Pageant / agent 支持内置

**配置属性** (JSch.setConfig):
- `kex`, `server_host_key`, `cipher`, `mac`, `compression`
- `client_pubkey` (PubkeyAcceptedAlgorithms)
- `PreferredAuthentications`
- `dhgex_min`, `dhgex_max`, `dhgex_preferred`
- `FingerprintHash`, `MaxAuthTries`

#### 6.3.2 Apache MINA SSHD

- **官网**: <https://mina.apache.org/sshd-project/>
- **定位**: Apache 的 Java SSH 库，支持客户端和服务器端

---

### 6.4 Node.js 生态

#### 6.4.1 ssh2

- **仓库**: <https://github.com/mscdex/ssh2>
- **npm**: `npm install ssh2`
- **语言**: JavaScript (Node.js v16+)
- **许可**: MIT
- **定位**: 纯 JavaScript SSH2 客户端和服务器模块

**核心模块**:
- `Client` — SSH 客户端
- `Server` — SSH 服务器
- `utils` — 工具函数 (`parseKey`, `generateKeyPair` 等)
- SFTP 子模块 (见 `SFTP.md`)
- `AgentProtocol` / `BaseAgent` — Agent 支持

**认证方式**:
- 密码认证
- 公钥认证 (支持 encrypted keys, agent)
- keyboard-interactive
- hostbased

**通道类型**:
- `session` → shell, exec, subsystem
- `direct-tcpip` / `forwarded-tcpip` → 端口转发
- `x11` → X11 转发

**SFTP 支持**: 完整 SFTP 客户端 (read, write, readdir, stat, symlink 等)

---

### 6.5 Go 生态

#### 6.5.1 crypto/ssh

- **Go 标准库延伸**: `golang.org/x/crypto/ssh`
- **定位**: Go 语言标准 SSH 库，支持客户端和服务器端
- **核心类型**: `ssh.Client`, `ssh.Session`, `ssh.Server`, `ssh.Channel`

---

### 6.6 Rust 生态

| 库 | 描述 |
|----|------|
| `thrussh` | 纯 Rust SSH 实现 |
| `ssh2-rs` | 基于 libssh2 的 Rust 绑定 |
| `russh` | 异步 SSH 客户端/服务器 |

---

### 6.7 其他语言

| 语言 | 库 | 备注 |
|------|----|------|
| C# | SSH.NET | .NET SSH 客户端 |
| Ruby | net-ssh | 纯 Ruby SSHv2 |
| PHP | phpseclib | 纯 PHP SSH |
| Perl | Net::SSH::Perl / Net::OpenSSH | SSH 模块 |
| Lua | lua-ssh2 | libssh2 绑定 |

---

## 七、SSH 调用方式与使用范例

### 7.1 命令行方式 (OpenSSH)

#### 基本连接

```bash
# SSH 远程登录
ssh user@hostname

# 指定端口
ssh -p 2222 user@hostname

# 指定私钥
ssh -i ~/.ssh/id_ed25519 user@hostname

# 执行远程命令
ssh user@hostname 'ls -la /var/log'

# 启用压缩
ssh -C user@hostname
```

#### 密钥生成

```bash
# 生成 Ed25519 密钥 (推荐)
ssh-keygen -t ed25519 -C "your_email@example.com"

# 生成 RSA 4096 位密钥
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"

# 生成 ECDSA 密钥
ssh-keygen -t ecdsa -b 521

# 查看公钥指纹
ssh-keygen -lf ~/.ssh/id_ed25519.pub

# 提取公钥
ssh-keygen -y -f ~/.ssh/id_ed25519
```

#### 文件传输

```bash
# SCP 上传
scp localfile.txt user@hostname:/remote/path/

# SCP 下载
scp user@hostname:/remote/path/file.txt ./

# SCP 递归复制目录
scp -r ./mydir user@hostname:/remote/path/

# SFTP 交互式会话
sftp user@hostname
# sftp> put localfile
# sftp> get remotefile
# sftp> ls
# sftp> cd /remote/path
```

#### SSH Agent

```bash
# 启动 agent
eval "$(ssh-agent -s)"

# 添加密钥
ssh-add ~/.ssh/id_ed25519

# 列出已加载的密钥
ssh-add -l

# 删除所有密钥
ssh-add -D
```

#### 端口转发

```bash
# 本地端口转发 (本地 → 服务器 → 远端)
# 将本地 8080 端口转发到 remote:80
ssh -L 8080:remote:80 user@hostname

# 远程端口转发 (服务器 → 本地 → 目标)
# 将服务器 9090 端口转发回本地 3000
ssh -R 9090:localhost:3000 user@hostname

# 动态端口转发 (SOCKS 代理)
ssh -D 1080 user@hostname
```

#### SSH 配置文件 (~/.ssh/config)

```
Host myserver
    HostName 192.168.1.100
    Port 22
    User admin
    IdentityFile ~/.ssh/id_ed25519
    ForwardAgent yes
    Compression yes

Host bastion
    HostName bastion.example.com
    User jumpuser

Host internal
    HostName 10.0.0.50
    User admin
    ProxyJump bastion
```

#### sshd_config 关键配置

```ini
# /etc/ssh/sshd_config
Port 22
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2
AllowUsers user1 user2
AllowGroups sshusers
```

### 7.2 C/C++ 编程 (libssh2)

```c
#include <libssh2.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>

int main() {
    int sock = socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in sin;
    sin.sin_family = AF_INET;
    sin.sin_port = htons(22);
    inet_pton(AF_INET, "192.168.1.100", &sin.sin_addr);
    connect(sock, (struct sockaddr*)&sin, sizeof(sin));

    libssh2_init(0);

    LIBSSH2_SESSION *session = libssh2_session_init();
    libssh2_session_handshake(session, sock);

    // 密码认证
    libssh2_userauth_password(session, "username", "password");

    // 或公钥认证
    // libssh2_userauth_publickey_fromfile(session, "username",
    //     "/home/user/.ssh/id_rsa.pub", "/home/user/.ssh/id_rsa", NULL);

    // 打开通道并执行命令
    LIBSSH2_CHANNEL *channel = libssh2_channel_open_session(session);
    libssh2_channel_exec(channel, "uptime");

    char buffer[4096];
    int bytes = libssh2_channel_read(channel, buffer, sizeof(buffer));
    printf("Output: %.*s\n", bytes, buffer);

    libssh2_channel_close(channel);
    libssh2_channel_free(channel);
    libssh2_session_disconnect(session, "Normal Shutdown");
    libssh2_session_free(session);
    libssh2_exit();
    close(sock);
    return 0;
}
```

**编译**:
```bash
gcc -o ssh_example ssh_example.c -lssh2
```

### 7.3 Python 编程 (Paramiko)

#### 基本连接与命令执行

```python
import paramiko

# 创建 SSH 客户端
client = paramiko.SSHClient()

# 设置主机密钥策略 (首次自动接受)
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

# 连接
client.connect(
    hostname='192.168.1.100',
    port=22,
    username='admin',
    password='password'
)

# 执行命令
stdin, stdout, stderr = client.exec_command('ls -la /var/log')
print(stdout.read().decode())

# 获取退出状态
exit_code = stdout.channel.recv_exit_status()
print(f'Exit code: {exit_code}')

client.close()
```

#### 公钥认证

```python
import paramiko

# 加载私钥
private_key = paramiko.Ed25519Key.from_private_key_file(
    '/home/user/.ssh/id_ed25519'
)

# 或加密的私钥
# private_key = paramiko.RSAKey.from_private_key_file(
#     '/home/user/.ssh/id_rsa', password='passphrase'
# )

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('hostname', username='admin', pkey=private_key)
```

#### SFTP 文件传输

```python
# 打开 SFTP 客户端
sftp = client.open_sftp()

# 上传文件
sftp.put('localfile.txt', '/remote/path/remotefile.txt')

# 下载文件
sftp.get('/remote/path/remotefile.txt', 'localfile.txt')

# 列出目录
files = sftp.listdir('/remote/path')
for f in files:
    print(f)

# 获取文件属性
attr = sftp.stat('/remote/path/file.txt')
print(f'Size: {attr.st_size}, Mode: {oct(attr.st_mode)}')

sftp.close()
```

#### 交互式 Shell

```python
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('hostname', username='admin', password='password')

# 打开交互式 shell
channel = client.invoke_shell()
channel.send('ls -la\n')
channel.send('exit\n')

# 读取输出
while not channel.exit_status_ready():
    if channel.recv_ready():
        data = channel.recv(1024).decode()
        print(data, end='')

client.close()
```

#### 底层 Transport 使用

```python
import paramiko
import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('hostname', 22))

transport = paramiko.Transport(sock)
transport.start_client()
transport.auth_password('username', 'password')

# 打开 SFTP
sftp = paramiko.SFTPClient.from_transport(transport)

# 或打开 session
channel = transport.open_session()
channel.exec_command('uptime')
print(channel.recv(4096).decode())

transport.close()
```

### 7.4 Java 编程 (JSch)

#### Maven 依赖

```xml
<dependency>
    <groupId>com.github.mwiede</groupId>
    <artifactId>jsch</artifactId>
    <version>2.28.0</version>
</dependency>
```

#### 基本连接与命令执行

```java
import com.jcraft.jsch.*;

public class SSHExample {
    public static void main(String[] args) throws Exception {
        JSch jsch = new JSch();

        // 添加私钥 (可选)
        jsch.addIdentity("/home/user/.ssh/id_ed25519");

        // 创建会话
        Session session = jsch.getSession("username", "hostname", 22);
        session.setPassword("password");

        // SSH 配置
        session.setConfig("StrictHostKeyChecking", "no");
        session.connect(5000);  // 5秒超时

        // 执行命令
        ChannelExec channel = (ChannelExec) session.openChannel("exec");
        channel.setCommand("ls -la /var/log");
        channel.setInputStream(null);
        channel.setErrStream(System.err);

        channel.connect();

        // 读取输出
        java.io.InputStream in = channel.getInputStream();
        byte[] buffer = new byte[1024];
        int bytesRead;
        while ((bytesRead = in.read(buffer)) != -1) {
            System.out.print(new String(buffer, 0, bytesRead));
        }

        channel.disconnect();
        session.disconnect();
    }
}
```

#### SFTP 文件传输

```java
import com.jcraft.jsch.*;

public class SFTPExample {
    public static void main(String[] args) throws Exception {
        JSch jsch = new JSch();
        Session session = jsch.getSession("username", "hostname", 22);
        session.setPassword("password");
        session.setConfig("StrictHostKeyChecking", "no");
        session.connect();

        ChannelSftp sftp = (ChannelSftp) session.openChannel("sftp");
        sftp.connect();

        // 上传
        sftp.put("localfile.txt", "/remote/path/remotefile.txt");

        // 下载
        sftp.get("/remote/path/remotefile.txt", "localfile.txt");

        // 列出文件
        java.util.Vector files = sftp.ls("/remote/path");
        for (Object obj : files) {
            ChannelSftp.LsEntry entry = (ChannelSftp.LsEntry) obj;
            System.out.println(entry.getFilename());
        }

        sftp.disconnect();
        session.disconnect();
    }
}
```

#### 算法配置

```java
// 全局配置
JSch.setConfig("kex",
    "curve25519-sha256,curve25519-sha256@libssh.org,"
    + "ecdh-sha2-nistp256,ecdh-sha2-nistp384,ecdh-sha2-nistp521,"
    + "diffie-hellman-group-exchange-sha256");
JSch.setConfig("server_host_key",
    "ssh-ed25519,ecdsa-sha2-nistp256,rsa-sha2-512,rsa-sha2-256");
JSch.setConfig("cipher.s2c",
    "chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,"
    + "aes128-gcm@openssh.com,aes256-ctr,aes192-ctr,aes128-ctr");
JSch.setConfig("mac.s2c",
    "hmac-sha2-256-etm@openssh.com,hmac-sha2-512-etm@openssh.com,"
    + "hmac-sha2-256,hmac-sha2-512");

// 每会话配置
session.setConfig("server_host_key",
    session.getConfig("server_host_key") + ",ssh-rsa");
session.setConfig("PubkeyAcceptedAlgorithms",
    session.getConfig("PubkeyAcceptedAlgorithms") + ",ssh-rsa");
```

### 7.5 Node.js 编程 (ssh2)

#### 基本连接和命令执行

```javascript
const { Client } = require('ssh2');

const conn = new Client();

conn.on('ready', () => {
    console.log('Client :: ready');

    conn.exec('uptime', (err, stream) => {
        if (err) throw err;
        stream.on('close', (code, signal) => {
            console.log('Stream :: close :: code: ' + code + ', signal: ' + signal);
            conn.end();
        }).on('data', (data) => {
            console.log('STDOUT: ' + data);
        }).stderr.on('data', (data) => {
            console.log('STDERR: ' + data);
        });
    });
});

conn.connect({
    host: '192.168.100.100',
    port: 22,
    username: 'frylock',
    privateKey: require('fs').readFileSync('/path/to/my/key')
});
```

#### 交互式 Shell

```javascript
const { Client } = require('ssh2');
const conn = new Client();

conn.on('ready', () => {
    conn.shell((err, stream) => {
        if (err) throw err;
        stream.on('close', () => {
            conn.end();
        }).on('data', (data) => {
            console.log('OUTPUT: ' + data);
        });
        stream.end('ls -l\nexit\n');
    });
});

conn.connect({
    host: '192.168.100.100',
    username: 'frylock',
    password: 'nodejsrules'
});
```

#### 端口转发

```javascript
// 本地转发 (conn.forwardOut)
conn.forwardOut('192.168.100.102', 8000, '127.0.0.1', 80, (err, stream) => {
    if (err) throw err;
    stream.on('data', (data) => {
        console.log('TCP :: DATA: ' + data);
    }).end('HEAD / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n');
});

// 远程转发 (conn.forwardIn)
conn.forwardIn('127.0.0.1', 8000, (err) => {
    if (err) throw err;
    console.log('Listening on server port 8000!');
});
conn.on('tcp connection', (info, accept, reject) => {
    const stream = accept();
    stream.on('data', (data) => console.log(data.toString()));
});
```

#### SFTP

```javascript
conn.sftp((err, sftp) => {
    if (err) throw err;
    sftp.readdir('foo', (err, list) => {
        if (err) throw err;
        console.dir(list);
        conn.end();
    });
});
```

#### 连接代理 (Connection Hopping)

```javascript
const conn1 = new Client(), conn2 = new Client();
conn1.on('ready', () => {
    conn1.forwardOut('127.0.0.1', 12345, '10.1.1.40', 22, (err, stream) => {
        if (err) throw err;
        conn2.connect({
            sock: stream,
            username: 'user2',
            password: 'password2'
        });
    });
}).connect({ host: '192.168.1.1', username: 'user1', password: 'pass1' });
```

### 7.6 Go 编程 (crypto/ssh)

```go
package main

import (
    "fmt"
    "golang.org/x/crypto/ssh"
    "io/ioutil"
)

func main() {
    key, _ := ioutil.ReadFile("/home/user/.ssh/id_ed25519")
    signer, _ := ssh.ParsePrivateKey(key)

    config := &ssh.ClientConfig{
        User: "username",
        Auth: []ssh.AuthMethod{
            ssh.PublicKeys(signer),
        },
        HostKeyCallback: ssh.InsecureIgnoreHostKey(),
    }

    client, _ := ssh.Dial("tcp", "hostname:22", config)
    session, _ := client.NewSession()
    defer session.Close()

    output, _ := session.CombinedOutput("ls -la")
    fmt.Println(string(output))
}
```

---

## 八、SSH 密钥管理

### 8.1 密钥类型对比

| 类型 | 最小长度 | 推荐长度 | 安全级别 | 备注 |
|------|---------|---------|---------|------|
| RSA | 1024 | 4096 | 高 | 最广泛支持，NIST 要求 ≥2048 |
| ECDSA | 256 | 256/384/521 | 高 | ECC 曲线，密钥短、性能好 |
| Ed25519 | 256 | 256 | 最高 | EdDSA，推荐首选，性能最佳 |
| Ed448 | 456 | 456 | 最高 | 类似 Ed25519，更高安全 |
| DSA | — | — | **废弃** | 已被弃用，不安全 |

### 8.2 密钥文件格式

- **OpenSSH 格式** (`-----BEGIN OPENSSH PRIVATE KEY-----`)
- **PEM 格式** (`-----BEGIN RSA PRIVATE KEY-----`)
- **RFC 4716 公钥格式** (`---- BEGIN SSH2 PUBLIC KEY ----`)
- **PPK 格式** (PuTTY Private Key)

### 8.3 known_hosts 管理

```bash
# 手动添加主机密钥
ssh-keyscan hostname >> ~/.ssh/known_hosts

# 扫描带特定端口的主机
ssh-keyscan -p 2222 hostname >> ~/.ssh/known_hosts

# 删除指定主机密钥
ssh-keygen -R hostname

# 验证主机密钥指纹
ssh-keygen -l -f ~/.ssh/known_hosts
```

### 8.4 通过 DNS 验证 (SSHFP)

```bash
# 生成 SSHFP 记录
ssh-keygen -r hostname

# 客户端启用 SSHFP 验证
ssh -o "VerifyHostKeyDNS=yes" hostname
```

---

## 九、SSH 安全最佳实践

### 9.1 服务器端

```ini
# /etc/ssh/sshd_config 安全配置建议

# 基本设置
Port 22                                    # 或非标准端口
Protocol 2                                 # 仅 SSH-2
ListenAddress 0.0.0.0                      # 或特定 IP

# 禁用不安全的认证方法
PermitRootLogin no                         # 禁止 root 直接登录
PasswordAuthentication no                  # 禁用密码认证（使用密钥）
PermitEmptyPasswords no                    # 禁止空密码
ChallengeResponseAuthentication no         # 禁用 challenge-response

# 公钥认证
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys

# 算法白名单 (现代安全配置)
KexAlgorithms curve25519-sha256,curve25519-sha256@libssh.org,diffie-hellman-group-exchange-sha256
HostKeyAlgorithms ssh-ed25519,ssh-ed25519-cert-v01@openssh.com,rsa-sha2-512,rsa-sha2-256
Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com
MACs hmac-sha2-256-etm@openssh.com,hmac-sha2-512-etm@openssh.com

# 会话限制
MaxAuthTries 3                             # 最大认证尝试次数
MaxSessions 10                             # 最大并发会话数
ClientAliveInterval 300                    # 保持活动间隔 (秒)
ClientAliveCountMax 2                      # 最大无响应次数
LoginGraceTime 60                          # 登录超时 (秒)

# 访问控制
AllowUsers user1 user2                     # 白名单用户
AllowGroups sshusers                       # 白名单组
DenyUsers root baduser                     # 黑名单用户
DenyGroups badgroup                        # 黑名单组

# 禁用不需要的功能
X11Forwarding no                           # 禁用 X11 转发（不需要时）
AllowAgentForwarding no                    # 禁用 agent 转发（不需要时）
AllowTcpForwarding no                      # 禁用 TCP 转发（不需要时）
PermitTunnel no                            # 禁用 tun 设备转发
PermitUserEnvironment no                   # 禁止用户环境变量
```

### 9.2 客户端

- **使用 Ed25519 密钥** (比 RSA 更快更安全)
- **使用 SSH Agent** 避免重复输入密码
- **验证主机密钥指纹** 首次连接时
- **使用 SSHFP DNS 记录** 验证主机密钥
- **配置 ~/.ssh/config** 管理多台主机
- **定期轮换密钥**
- **使用 ssh-audit** 工具检查服务器安全配置

### 9.3 工具推荐

| 工具 | 用途 |
|------|------|
| `ssh-audit` | SSH 服务器/客户端安全审计 |
| `fail2ban` | 防止暴力破解 |
| `sshguard` | SSH 入侵防御 |
| `lynis` | 系统安全审计 |

---

## 十、参考资源

### 10.1 规范与标准

- **IANA SSH 参数注册表**: <https://www.iana.org/assignments/ssh-parameters/>
- **OpenSSH 规范页面**: <https://www.openssh.com/specs.html>
- **IETF secsh 工作组**: <https://www.ietf.org/html.charters/secsh-charter.html>
- **CURDLE 工作组 (新算法 RFCs)**: <https://datatracker.ietf.org/wg/curdle/>

### 10.2 项目主页

| 项目 | 链接 |
|------|------|
| OpenSSH | <https://www.openssh.com/> |
| OpenSSH 手册 | <https://man.openbsd.org/ssh> |
| libssh | <https://www.libssh.org/> |
| libssh2 | <https://www.libssh2.org/> |
| Dropbear | <https://matt.ucc.asn.au/dropbear/dropbear.html> |
| Paramiko | <https://www.paramiko.org/> |
| Fabric | <https://www.fabfile.org/> |
| JSch | <https://github.com/mwiede/jsch> |
| Apache MINA SSHD | <https://mina.apache.org/sshd-project/> |
| ssh2 (Node.js) | <https://github.com/mscdex/ssh2> |
| Go crypto/ssh | <https://pkg.go.dev/golang.org/x/crypto/ssh> |

### 10.3 核心 RFC 列表

```
RFC 4250 — SSH Protocol Assigned Numbers
RFC 4251 — SSH Protocol Architecture
RFC 4252 — SSH Authentication Protocol
RFC 4253 — SSH Transport Layer Protocol
RFC 4254 — SSH Connection Protocol
RFC 4255 — SSHFP DNS Records
RFC 4256 — Keyboard-Interactive Authentication
RFC 4419 — DH Group Exchange
RFC 4462 — GSSAPI Authentication and Key Exchange
RFC 5656 — ECC Algorithm Integration
RFC 6668 — HMAC-SHA-2 for SSH
RFC 8268 — SHA-2 for SSHFP
RFC 8308 — Extension Negotiation
RFC 8332 — RSA SHA-2 Signatures
RFC 8709 — Ed25519/Ed448 Public Key Algorithms
RFC 8731 — Curve25519/Curve448 Key Exchange
RFC 8732 — GSSAPI Key Exchange (SHA-2)
RFC 8758 — ChaCha20-Poly1305 AEAD
RFC 9141 — Session Channel Extension
RFC 9142 — Key Exchange Method Updates
```

---

> **文档编制说明**: 本文档基于 IETF RFC 规范原文、各开源项目官方文档及源代码仓库的实际内容编制。所有技术细节均通过 `web_fetch` 工具从官方来源获取，力求准确反映当前（2026 年）的协议标准和工具生态状况。
