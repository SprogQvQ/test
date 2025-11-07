# Splunk Universal Forwarder 批量安装工具

这是一个用于批量在远程服务器上安装 Splunk Universal Forwarder (UF) 的 Python 脚本，设计时充分考虑了业务稳定性和安全性。

## ✨ 主要特性

- 🔄 **批量安装**: 支持同时在多台服务器上安装
- 🚦 **并发控制**: 可配置最大并发数，避免同时处理过多服务器
- ⏱️ **批次延迟**: 批次间可设置延迟，进一步降低对业务的影响
- 🔍 **资源检查**: 安装前检查内存、磁盘空间，确保资源充足
- 🛡️ **安全连接**: 支持密码和SSH密钥两种认证方式
- 📊 **详细日志**: 完整的操作日志和安装结果统计
- ✅ **幂等性**: 自动检测已安装的服务器，避免重复安装
- 🧹 **自动清理**: 安装完成后自动清理临时文件

## 📋 前置要求

### 1. Python 环境
- Python 3.6 或更高版本

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 服务器要求
远程服务器需要满足：
- 开启 SSH 访问
- 具有 root 或 sudo 权限的账户
- 足够的磁盘空间 (至少 2GB)
- 足够的内存 (至少 512MB 可用)
- 已安装 `wget` 或 `curl` 命令

## 🔧 配置说明

编辑 `config.json` 文件进行配置：

### Splunk 配置
```json
{
  "splunk_config": {
    "download_url": "Splunk UF 安装包的下载地址",
    "deployment_server": "Splunk Deployment Server 地址:端口",
    "receiving_indexer": "Splunk Indexer 地址:端口"
  }
}
```

**下载地址获取方式**：
1. 访问 [Splunk 官网](https://www.splunk.com/en_us/download/universal-forwarder.html)
2. 选择对应的操作系统和版本
3. 获取下载链接（可能需要登录）

### 服务器列表
```json
{
  "servers": [
    {
      "host": "服务器IP或域名",
      "port": 22,
      "username": "登录用户名",
      "password": "密码（如果使用密钥则留空）",
      "key_file": "SSH私钥文件路径（如果使用密码则留空）",
      "os_type": "linux"
    }
  ]
}
```

### 并发和资源控制
```json
{
  "max_concurrent_installs": 3,           // 最大并发安装数
  "delay_between_batches_seconds": 10,    // 批次间延迟（秒）
  "force_reinstall": false,               // 是否强制重装
  "cleanup_after_install": true,          // 安装后清理临时文件
  "resource_limits": {
    "min_memory_mb": 512,                 // 最小可用内存（MB）
    "min_disk_mb": 2048                   // 最小可用磁盘空间（MB）
  }
}
```

## 🚀 使用方法

### 1. 测试连接（推荐）
在正式安装前，先进行连接测试：
```bash
python install_splunk_uf.py --dry-run
```

### 2. 正式安装
```bash
python install_splunk_uf.py
```

### 3. 使用自定义配置文件
```bash
python install_splunk_uf.py -c /path/to/your/config.json
```

## 📊 输出说明

### 1. 控制台输出
脚本会实时输出安装进度和状态信息。

### 2. 日志文件
每次运行都会生成时间戳命名的日志文件：
- 格式: `splunk_install_YYYYMMDD_HHMMSS.log`
- 包含详细的操作记录和错误信息

### 3. 结果文件
安装完成后会生成JSON格式的结果文件：
- 格式: `install_results_YYYYMMDD_HHMMSS.json`
- 包含每台服务器的安装状态

## 🛡️ 安全最佳实践

### 1. 密码管理
**不要将密码直接写在配置文件中**，建议：
- 使用 SSH 密钥认证（推荐）
- 使用环境变量存储密码
- 使用专门的密码管理工具

### 2. SSH 密钥配置示例
```bash
# 生成SSH密钥对
ssh-keygen -t rsa -b 4096 -f ~/.ssh/splunk_deploy

# 复制公钥到目标服务器
ssh-copy-id -i ~/.ssh/splunk_deploy.pub root@target_server

# 在配置文件中使用私钥
{
  "key_file": "/home/user/.ssh/splunk_deploy",
  "password": ""
}
```

### 3. 文件权限
```bash
# 限制配置文件权限
chmod 600 config.json

# 限制脚本权限
chmod 700 install_splunk_uf.py
```

## ⚙️ 业务影响最小化策略

### 1. 控制并发数
```json
"max_concurrent_installs": 3
```
- 建议设置为 3-5 台并发
- 根据网络和服务器性能调整

### 2. 设置批次延迟
```json
"delay_between_batches_seconds": 10
```
- 建议设置 10-30 秒延迟
- 给系统足够的恢复时间

### 3. 选择合适的时间窗口
- 在业务低峰期执行（如凌晨）
- 避免在业务高峰期操作
- 制定应急回滚计划

### 4. 分批执行
将服务器分成多个批次，逐批安装：
```bash
# 第一批：测试服务器
python install_splunk_uf.py -c config_batch1.json

# 观察一段时间后，执行第二批
python install_splunk_uf.py -c config_batch2.json
```

### 5. 资源监控
脚本会自动检查：
- CPU 负载
- 内存使用情况
- 磁盘空间

如果资源不足，会跳过该服务器并记录日志。

## 🔍 故障排查

### 问题 1: SSH 连接失败
**可能原因**：
- 网络不通
- 防火墙阻止
- SSH 服务未启动
- 认证信息错误

**解决方法**：
```bash
# 手动测试连接
ssh -v username@host

# 检查防火墙
sudo iptables -L

# 检查SSH服务
systemctl status sshd
```

### 问题 2: 下载失败
**可能原因**：
- 网络问题
- 下载链接失效
- wget/curl 未安装

**解决方法**：
- 检查下载 URL 是否有效
- 考虑使用内网文件服务器
- 手动下载后通过 SCP 传输

### 问题 3: 权限不足
**可能原因**：
- 用户没有 sudo 权限
- 目录权限限制

**解决方法**：
- 使用 root 用户
- 或配置 sudo 免密码

### 问题 4: 资源不足
**可能原因**：
- 内存不足
- 磁盘空间不足

**解决方法**：
- 清理磁盘空间
- 调整配置文件中的资源阈值（不推荐）

## 📝 安装流程说明

脚本执行以下步骤：

1. **建立 SSH 连接** - 连接到远程服务器
2. **检查安装状态** - 确认是否已安装 Splunk UF
3. **资源检查** - 验证内存和磁盘空间是否充足
4. **下载安装包** - 从指定 URL 下载 Splunk UF
5. **执行安装** - 根据操作系统类型执行安装命令
6. **配置服务** - 配置 Deployment Server 和 Receiving Indexer
7. **启用开机自启** - 设置 Splunk UF 随系统启动
8. **清理临时文件** - 删除下载的安装包

## 🔄 高级用法

### 1. 使用内网文件服务器
如果有内网文件服务器，可以先下载 Splunk 安装包到本地服务器，然后修改下载 URL：
```json
{
  "download_url": "http://internal-fileserver.local/splunk/splunkforwarder-9.1.2.tgz"
}
```

### 2. 自定义安装路径
需要修改脚本中的安装路径（默认 `/opt/splunkforwarder`）

### 3. 批量配置不同的 Splunk 设置
可以为不同服务器组准备多个配置文件。

## 📞 技术支持

如遇到问题，请提供以下信息：
- 日志文件内容
- 目标服务器操作系统版本
- 错误信息截图
- 配置文件（隐藏敏感信息）

## ⚠️ 注意事项

1. **备份重要数据**: 在操作前备份重要配置和数据
2. **测试环境验证**: 先在测试环境验证脚本功能
3. **逐步推进**: 分批次、小规模开始，逐步扩大范围
4. **监控告警**: 安装过程中保持对业务系统的监控
5. **回滚准备**: 准备好回滚方案和脚本
6. **通知相关人员**: 提前通知运维和业务团队

## 📜 许可证

请查看 LICENSE 文件了解详情。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！
