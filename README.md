# DeepSeek Usage

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2023.1%2B-blue.svg)](https://www.home-assistant.io/)

Home Assistant 自定义集成，用于在仪表盘上实时显示 **DeepSeek API 余额**。

> DeepSeek 官方目前仅提供余额查询接口（`/user/balance`），暂不提供按调用量/按模型的用量明细。本集成会每小时自动拉取一次余额，并拆分为总余额、赠送余额、充值余额三个传感器。

---

## 功能

- ✅ 纯 UI 配置，无需编辑 `configuration.yaml`
- ✅ 配置时自动验证 API Key 有效性
- ✅ 支持自定义刷新间隔（默认 1 小时）
- ✅ 余额传感器带 `device_class: monetary` + `state_class: total`，可直接用于 ApexCharts 历史统计
- ✅ 余额不足/不可用时自动标记 `unavailable`

---

## 实体列表

配置完成后自动生成以下传感器：

| 实体 | 说明 | 单位 |
|---|---|---|
| `sensor.deepseek_total_balance` | 总余额 | CNY |
| `sensor.deepseek_granted_balance` | 赠送余额 | CNY |
| `sensor.deepseek_topped_up_balance` | 充值余额 | CNY |
| `sensor.deepseek_is_available` | 余额是否可用 | on / off |

---

## 安装

### 方式一：手动安装（推荐，最快）

1. 下载 [最新 Release](https://github.com/SagisawaTsubasa/DeepSeek-HA-Usage/releases/latest) 并解压。
2. 将 `custom_components/deepseek_usage/` 复制到 Home Assistant 的 `config/custom_components/` 目录下。
3. 重启 Home Assistant。
4. 进入 **设置 > 设备与服务 > 添加集成**，搜索 **DeepSeek Usage**。
5. 输入你的 DeepSeek API Key，完成配置。

### 方式二：通过 HACS 安装

1. 打开 HACS，点击右上角 **自定义仓库**。
2. 仓库类型选 **Integration**，填入本仓库地址：`https://github.com/SagisawaTsubasa/DeepSeek-HA-Usage`。
3. 点击 **下载**，选择最新版本。
4. 重启 Home Assistant。
5. 进入 **设置 > 设备与服务 > 添加集成**，搜索 **DeepSeek Usage**。

---

## 配置选项

集成添加后，点击卡片上的 **配置 > 选项** 可修改：

- **更新间隔**：默认 `3600` 秒（1 小时），范围 `60 ~ 86400` 秒。修改后无需重启 HA。

---

## 仪表盘示例

```yaml
type: entities
entities:
  - entity: sensor.deepseek_total_balance
    name: 总余额
  - entity: sensor.deepseek_granted_balance
    name: 赠送余额
  - entity: sensor.deepseek_topped_up_balance
    name: 充值余额
  - entity: sensor.deepseek_is_available
    name: 状态
title: DeepSeek API 余额
```

---

## 常见问题

**Q: 为什么看不到 token 消耗量？**
> DeepSeek 官方 API 目前只开放 `/user/balance` 余额查询，没有历史用量或按模型统计接口。如需统计每次调用的 token，建议在调用端（如 Node-RED、Python 脚本）自行将 `usage` 字段写回 HA 的 `input_number`。

**Q: 支持第三方中转（如硅基流动、OpenRouter）吗？**
> 当前仅支持 DeepSeek 官方端点。如需兼容中转，可 fork 后修改 `coordinator.py` 中的 `resource` URL。

**Q: 刷新间隔最低能设多少？**
> 60 秒。不建议低于 300 秒，避免触发限流。

---

## 许可证

MIT License
