/*!
 * MEF-Core Utilities
 * 
 * Core utility modules providing foundational functionality across the MEF workspace.
 */

pub mod geometry;
pub mod field_vector;

pub use geometry::{Node, canonical_nodes, canonical_edges, get_metatron_nodes, get_metatron_edges};
pub use field_vector::FieldVector;

#[cfg(test)]
mod tests {
    #[test]
    fn it_works() {
        let result = 2 + 2;
        assert_eq!(result, 4);
    }
}
