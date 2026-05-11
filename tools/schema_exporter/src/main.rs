use niri_ipc::{Action, Event, Reply, Request};
use schemars::schema_for;
use std::path::PathBuf;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let output_dir = if args.len() > 2 && args[1] == "--output-dir" {
        PathBuf::from(&args[2])
    } else {
        PathBuf::from("schema/exported")
    };

    std::fs::create_dir_all(&output_dir).expect("Failed to create output directory");

    macro_rules! write_schema {
        ($name:expr, $type:ty) => {{
            let path = output_dir.join(format!("{}.schema.json", $name));
            let schema = serde_json::to_value(schema_for!($type)).unwrap();
            let json = serde_json::to_string_pretty(&schema).unwrap();
            std::fs::write(&path, &json).unwrap();
            println!("{}", path.display());
        }};
    }

    write_schema!("request", Request);
    write_schema!("reply", Reply);
    write_schema!("event", Event);
    write_schema!("action", Action);
}
