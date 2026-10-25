fn main() {
    println!("cargo:rerun-if-env-changed=SILICIUM_RELEASE_VERSION");
    println!("cargo:rerun-if-env-changed=SILICIUM_RELEASE_CHANNEL");
    println!("cargo:rerun-if-env-changed=SILICIUM_RELEASE_BUILD");
    println!("cargo:rerun-if-env-changed=SILICIUM_UPDATE_MANIFEST_URL");
    tauri_build::build();
}
