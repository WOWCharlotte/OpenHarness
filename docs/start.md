# 快速开始指南

本指南介绍如何安装环境、配置 MiniMax 节点并启动 OpenHarness。

## 环境准备

### 1. 安装依赖

```bash
# 克隆项目
git clone https://github.com/WOWCharlotte/OpenHarness.git
cd OpenHarness

# 使用 uv 安装（推荐）
uv sync --extra dev

```

### 2. 验证安装

```bash
uv run oh --version
```

## 配置 MiniMax 节点

### 步骤 1：添加自定义 provider

```bash
uv run oh provider add minimax-endpoint \
  --label "MiniMax" \
  --provider anthropic \
  --api-format openai \
  --auth-source anthropic_api_key \
  --model minimax-m2.7 \
  --base-url https://api.minimaxi.com/v1
```

参数说明：
- `--provider anthropic`: 使用 Anthropic 兼容格式
- `--api-format openai`: MiniMax 使用 OpenAI 兼容的 Bearer Token 认证
- `--base-url https://api.minimaxi.com/v1`: MiniMax API 地址
- `--model minimax-m2.7`: MiniMax 模型

### 步骤 2：存储 API Key

```python
from openharness.auth.storage import store_credential

api_key = 'your-api-key'
store_credential('profile:minimax-endpoint', 'api_key', api_key)
store_credential('anthropic', 'api_key', api_key)
```

### 步骤 3：激活 provider

```bash
uv run oh provider use minimax-endpoint
```

### 查看配置状态

```bash
# 查看所有 provider
uv run oh provider list

# 查看认证状态
uv run oh auth status
```

## 启动应用

### 交互模式（默认）

```bash
uv run oh
```

### 带提示的打印模式

```bash
uv run oh -p "你的问题"
```

### 指定模型

```bash
uv run oh --model minimax-m2.7
```

### 复用历史会话

```bash
uv run oh --continue
```

## 故障排除

### 401 认证错误

如果遇到 `login fail: Please carry the API secret key` 错误：

1. 确认 `api_format` 是 `openai`（而非 `anthropic`）
2. 确认 base_url 正确：`https://api.minimaxi.com/v1`
3. 确认 API key 格式正确（MiniMax 使用 `sk-cp-` 前缀）

修复 api_format：
```bash
uv run python -c "from openharness.auth.manager import AuthManager; AuthManager().update_profile('minimax-endpoint', api_format='openai')"
```

### No API key configured

1. 检查环境变量：
```bash
echo $ANTHROPIC_API_KEY
echo $OPENAI_API_KEY
```

2. 重新登录：
```bash
oh auth login
```

3. 手动存储凭证：
```python
from openharness.auth.storage import store_credential
store_credential('anthropic', 'api_key', 'your-api-key')
```

## 配置概览

配置文件位于 `~/.openharness/` 目录：

| 文件 | 说明 |
|------|------|
| `settings.json` | 主配置文件（包含 base_url、api_format 等） |
| `credentials.json` | 敏感信息存储（API keys） |

### 关键配置项

```json
{
  "active_profile": "minimax-endpoint",
  "api_format": "openai",
  "profiles": {
    "minimax-endpoint": {
      "provider": "anthropic",
      "api_format": "openai",
      "base_url": "https://api.minimaxi.com/v1",
      "auth_source": "anthropic_api_key"
    }
  }
}
```