// A new migration file is not a change to any Rust source, so tell cargo to rebuild when the
// migrations folder changes. Otherwise a build could embed yesterday's migrations.
fn main() {
    println!("cargo:rerun-if-changed=migrations");
}
