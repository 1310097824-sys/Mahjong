# Mahjong Rust Core

底层高频计算核心。当前第一阶段只接管无副露牌型的 34 枚计数、向听数与弃牌后有效进张枚举，Python 侧保留完整规则兜底。

## 模块

- `tiles.rs`：牌 ID、34 种牌计数、三麻合法牌过滤。
- `shanten.rs`：标准形、七对子、国士无双向听数。
- `analysis.rs`：有效进张枚举、AI 前瞻用摸牌候选枚举、候选弃牌批量预计算、手牌路线特征分析。
- `ffi.rs`：供 Python `ctypes` 调用的 C ABI。

## 构建

```powershell
cd rust_core
cargo build --release
```

生成的动态库会被 `app/rust_core.py` 自动发现；缺失时系统会回退到原 Python 实现。
