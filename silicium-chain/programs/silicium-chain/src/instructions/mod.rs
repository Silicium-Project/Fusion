"""Groups the instruction modules."""

pub mod init_config;
pub mod register_worker;
pub mod submit_task;
pub mod fund_task;
pub mod assign_work;
pub mod submit_result;
pub mod verify_result;
pub mod finalize_task;
pub mod claim_reward;
pub mod slash_worker;

pub use init_config::*;
pub use register_worker::*;
pub use submit_task::*;
pub use fund_task::*;
pub use assign_work::*;
pub use submit_result::*;
pub use verify_result::*;
pub use finalize_task::*;
pub use claim_reward::*;
pub use slash_worker::*;
