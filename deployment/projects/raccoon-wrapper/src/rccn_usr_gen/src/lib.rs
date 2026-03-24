use std::path::Path;

use xtce_rs::{mdb::MissionDatabase, parser};


pub fn gen_parameters() -> MissionDatabase {
    let files = [
        "test_data/dt.xml",
        "test_data/base.xml",
        "test_data/parameters-dt-v2.xml",
    ].map(Path::new);

    parser::parse_files(&files).unwrap()
}

#[cfg(test)]
mod tests {
    use xtce_rs::mdb::{NamedItem, QualifiedName};

    use super::*;

    #[test]
    fn test_gen_parameters() {
        let mut mdb = gen_parameters();
        let name_db = &mdb.name_db().clone();

        let qualified_name = QualifiedName::from_str(name_db, "/parameters-dt").unwrap();
        let sys = mdb.get_space_system(&qualified_name).unwrap();

        for (_name, idx) in sys.parameters.iter() {
            let param = mdb.get_parameter(*idx);
            let name = mdb.name2str(param.name());
            println!("Param {:?}", name);

        }
    }
}
