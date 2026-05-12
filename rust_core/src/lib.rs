//! Mahjong Rust core.
//!
//! 这个 crate 只承接“纯计算、可批量、性能敏感”的后端逻辑，例如向听数、
//! 进张、风险表、EV 数值公式和基础规则工具。完整牌局状态、动作合法性和
//! 中文解释仍保留在 Python，Rust 通过 `ffi` 模块暴露 C ABI 给 `app/rust_core.py`
//! 调用。这样的边界让系统既能逐步提速，也不牺牲规则调试效率。

pub mod analysis;
pub mod ev;
pub mod ffi;
pub mod risk;
pub mod rules;
pub mod scoring;
pub mod shanten;
pub mod shape;
pub mod tiles;
