# DeepSeek Usage

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2023.1%2B-blue.svg)](https://www.home-assistant.io/)

Home Assistant 自定义集成，用于在仪表盘上实时显示 **DeepSeek API 余额** 及 **多时间维度消耗量**，并支持 **手动记录充值** 以修正消耗统计。

> DeepSeek 官方目前仅提供余额查询接口（`/user/balance`），暂不提供按调用量/按模型的用量明细。本集成通过持续记录余额快照，自动计算最近 30 分钟 / 3 小时 / 今日 / 昨日 / 本周 / 最近刷新周期 的消耗金额。充值后通过服务记录充值金额，消耗统计自动扣除充值部分，避免余额上升导致测定错误。

---

## 功能

- ✅ 纯 UI 配置，无需编辑 `configuration.yaml`
- ✅ 配置时自动验证 API Key 有效性
- ✅ 支持自定义刷新间隔（默认 1 小时）
- ✅ 余额传感器带 `device_class: monetary` + `state_class: total`
- ✅ **多时间窗口消耗**：30 分钟 / 3 小时 / 今日 / 昨日 / 本周 / 最近周期
- ✅ **手动充值记录**：通过服务调用记录充值，消耗统计自动修正
- ✅ 历史数据持久化，重启 HA 不丢失基准
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
| `sensor.deepseek_consumed` | 最近一个刷新周期消耗 | CNY |
| `sensor.deepseek_consumed_30m` | **最近 30 分钟消耗** | CNY |
| `sensor.deepseek_consumed_3h` | **最近 3 小时消耗** | CNY |
| `sensor.deepseek_consumed_today` | **今日消耗** | CNY |
| `sensor.deepseek_consumed_yesterday` | **昨日消耗** | CNY |
| `sensor.deepseek_consumed_week` | **本周消耗** | CNY |
| `sensor.deepseek_total_recharge` | **累计记录充值金额** | CNY |

---

## 安装

### 通过 HACS 安装

1. 打开 HACS，点击右上角 **自定义仓库**。
2. 仓库类型选 **Integration**，填入本仓库地址：`https://github.com/SagisawaTsubasa/DeepSeek-HA-Usage`。
3. 点击 **下载**，选择最新版本。
4. 重启 Home Assistant。
5. 进入 **设置 > 设备与服务 > 添加集成**，搜索 **DeepSeek Usage**。

---

## 配置选项

集成添加后，点击卡片上的 **配置 > 选项** 可修改：

- **更新间隔**：默认 `3600` 秒（1 小时），范围 `60 ~ 86400` 秒。修改后无需重启 HA。

> 建议：如果需要 `30 分钟消耗` 更精确，可把刷新间隔设为 1800 秒（30 分钟）或更短；但不宜低于 300 秒，避免触发限流。

---

## 充值记录

当你给 DeepSeek 充值后，余额会上升，导致消耗统计暂时为 0。此时需要手动记录充值金额，系统会自动修正后续消耗计算。

### 方式一：开发者工具调用服务

进入 **开发者工具 > 服务**，调用：

```yaml
service: deepseek_usage.record_recharge
data:
  amount: 50.0
```

`amount` 为充值金额（CNY），必须大于 0。

### 方式二：自动化脚本

```yaml
alias: 记录 DeepSeek 充值
sequence:
  - service: deepseek_usage.record_recharge
    data:
      amount: 50.0
mode: single
```

### 方式三：Node-RED / 脚本调用

任何能调用 HA Service 的端点都可以触发。记录后 `sensor.deepseek_total_recharge` 会累加，且所有时间窗口的消耗量会自动扣除该笔充值。

---

## 仪表盘示例

### 余额趋势 + 多维度消耗

```yaml
type: custom:layout-card
layout_type: custom:grid-layout
layout:
  grid-template-columns: 25% 75%
  margin: 0px
cards:
  - type: custom:mini-graph-card
    entities:
      - sensor.deepseek_total_balance
    height: 40
    hours_to_show: 48
    points_per_hour: 0.25
    line_width: 1
    smoothing: true
    decimals: 1
    font_size: 10
    color_thresholds:
      - value: 5
        color: "#ef5350"
      - value: 20
        color: "#66bb6a"
    show:
      name: false
      icon: false
      state: true
      labels: false
      points: false
    card_mod:
      style: |
        ha-card { padding: 4px 8px !important; }
  - type: entities
    entities:
      - entity: sensor.deepseek_consumed_today
        name: 今日
      - entity: sensor.deepseek_consumed_yesterday
        name: 昨日
      - entity: sensor.deepseek_consumed_3h
        name: 3小时
      - entity: sensor.deepseek_consumed_30m
        name: 30分钟
      - entity: sensor.deepseek_total_recharge
        name: 累计充值
      - entity: sensor.deepseek_total_balance
        name: 余额
    title: DeepSeek 用量
```

---

## 常见问题

**Q: 为什么看不到 token 消耗量？**
> DeepSeek 官方 API 目前只开放 `/user/balance` 余额查询，没有历史用量或按模型统计接口。所有消耗数据均通过对比余额快照计算得出。

**Q: 充值后消耗量显示为 0？**
> 记录充值前会显示 0，因为系统无法区分充值与消耗。调用 `deepseek_usage.record_recharge` 记录充值金额后，所有窗口的消耗统计会自动修正。

**Q: 支持第三方中转（如硅基流动、OpenRouter）吗？**
> 当前仅支持 DeepSeek 官方端点。如需兼容中转，可 fork 后修改 `coordinator.py` 中的 `resource` URL。

**Q: 刷新间隔最低能设多少？**
> 60 秒。不建议低于 300 秒，避免触发限流。30 分钟/3 小时等窗口的计算不依赖刷新间隔，历史数据会保留 8 天。

**Q: 昨日消耗显示为 unavailable？**
> 如果插件是第一天使用，没有昨天的历史余额数据，昨日消耗会显示 `unavailable`。运行满 24 小时后，跨天即可正常计算。

---

## 致谢

本集成由 [Kimi](https://kimi.moonshot.cn) 协助开发。

---

## 许可证

MIT License
