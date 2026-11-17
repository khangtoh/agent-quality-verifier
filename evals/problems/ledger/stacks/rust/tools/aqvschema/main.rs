//! Builds a fresh database at the given path the way the service does (every migration, in
//! order), for the Agent Quality Verifier (D5, D6). The verifier then reads the schema back from
//! that file. Built only with `--features aqvtools`.

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 2 {
        eprintln!("usage: aqvschema DATABASE");
        std::process::exit(2);
    }
    if let Err(err) = ledger::store::open(&args[1]) {
        eprintln!("{err}");
        std::process::exit(1);
    }
}
