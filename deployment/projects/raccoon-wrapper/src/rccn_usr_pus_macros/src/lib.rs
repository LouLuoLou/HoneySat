use proc_macro::TokenStream;
use quote::quote;
use syn::{parse_macro_input, punctuated::Punctuated, Data, DeriveInput, Fields, Meta, NestedMeta, Type};

/// Derives the PusParameters trait implementation for a struct.
///
/// This derive macro supports two types of parameter structs:
///
/// 1. Regular parameter structs where each field represents a spacecraft parameter
///    and must be annotated with a `#[hash]` attribute specifying a unique 32-bit identifier.
///
/// 2. Aggregate structs marked with `#[aggregate]` that contain only fields implementing
///    PusParameters. These structs forward parameter requests to their fields until one succeeds.
///
/// # Supported Field Types (for regular parameter structs)
/// - `f32`: 32-bit floating point
/// - `u8`: 8-bit unsigned integer
/// - `u16`: 16-bit unsigned integer
/// - `u32`: 32-bit unsigned integer
/// - `u64`: 64-bit unsigned integer
/// - `i8`: 8-bit signed integer
/// - `i16`: 16-bit signed integer
/// - `i32`: 32-bit signed integer
/// - `i64`: 64-bit signed integer
///
/// # Example
/// ```
/// #[derive(PusParameters)]
/// struct MyParameters {
///     #[hash(0xABCD0001)]
///     temperature: f32,
///     #[hash(0xABCD0002)] 
///     voltage: u16,
/// }
/// ```
#[proc_macro_derive(PusParameters, attributes(hash, aggregate))]
pub fn derive_pus_parameters(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as DeriveInput);
    let name = input.ident;

    let fields = match input.data {
        Data::Struct(data) => match data.fields {
            Fields::Named(fields) => fields.named,
            _ => panic!("Only named fields are supported"),
        },
        _ => panic!("Only structs are supported"),
    };

    // Check if this is an aggregate struct
    let is_aggregate = input.attrs.iter().any(|attr| attr.path.is_ident("aggregate"));

    let expanded = if is_aggregate {
        generate_aggregate_impl(&name, fields)
    } else {
        generate_parameter_impl(&name, fields)
    };

    TokenStream::from(expanded)
}

fn generate_aggregate_impl(name: &syn::Ident, fields: Punctuated<syn::Field, syn::token::Comma>) -> proc_macro2::TokenStream {
    let mut get_parameter_tries = quote!();
    let mut set_parameter_tries = quote!();

    for field in fields {
        let field_name = field.ident.unwrap();
        
        // Add try for get_parameter
        get_parameter_tries.extend(quote! {
            if let Ok(size) = self.#field_name.get_parameter_as_be_bytes(hash, writer) {
                return Ok(size);
            }
        });
        
        // Add try for set_parameter
        set_parameter_tries.extend(quote! {
            if self.#field_name.set_parameter_from_be_bytes(hash, buffer) {
                return true;
            }
        });
    }

    quote! {
        impl PusParameters for #name {
            fn get_parameter_as_be_bytes(
                &self,
                hash: u32,
                writer: &mut BitWriter,
            ) -> Result<usize, ParameterError> {
                #get_parameter_tries
                Err(ParameterError::UnknownParameter(hash))
            }

            fn set_parameter_from_be_bytes(&mut self, hash: u32, buffer: &mut BitBuffer) -> bool {
                #set_parameter_tries
                false
            }

            fn get_parameter_size(&self, _hash: u32) -> Option<usize> {
                None
            }
        }
    }
}

fn generate_parameter_impl(name: &syn::Ident, fields: Punctuated<syn::Field, syn::token::Comma>) -> proc_macro2::TokenStream {
    let mut get_param_matches = quote!();
    let mut set_param_matches = quote!();

    for field in fields {
        let field_name = field.ident.unwrap();
        let field_type = &field.ty;

        let attr = field
            .attrs
            .iter()
            .find(|attr| attr.path.is_ident("hash"))
            .expect(&format!(
                "Field {} missing #[hash] attribute",
                field_name
            ));

        let meta = attr.parse_meta().unwrap();
        let hash = match meta {
            Meta::List(list) => {
                let nested: Vec<NestedMeta> = list.nested.into_iter().collect();
                match nested.get(0) {
                    Some(NestedMeta::Lit(hash)) => hash.clone(),
                    _ => panic!("Expected #[hash(0x...)]"),
                }
            }
            _ => panic!("Expected #[hash(0x...)]"),
        };

        let set_conversion = match field_type {
            Type::Path(type_path) => {
                let type_ident = type_path.path.get_ident().unwrap();
                let type_name = type_ident.to_string();
                // Special handling for floating point types
                if type_name == "f32" {
                    quote! {
                        let val = f64::from_be_bytes(bytes);
                        self.#field_name = val as f32;
                    }
                } else if type_name == "f64" {
                    quote! {
                        self.#field_name = f64::from_be_bytes(bytes);
                    }
                } else if type_name.len() == 3 {
                    // Handle integer types by parsing the bit size from type name
                    let bits: usize = type_name[1..].parse().unwrap_or(0);
                    if bits > 0 && bits <= 64 {
                        quote! {
                            let start = ((64 - #bits) as usize).div_ceil(8);
                            self.#field_name = #type_ident::from_be_bytes(bytes[start..].try_into().unwrap());
                        }
                    } else {
                        panic!("Unsupported field `{}` type {}", field_name, type_name)
                    }
                } else {
                    panic!("Unsupported field `{}` type {}", field_name, type_name)
                }
            }
            _ => panic!("Unsupported field type"),
        };

        get_param_matches.extend(quote! {
            #hash => {
                let val = self.#field_name.to_be_bytes();
                writer.write_bytes(&val)
                    .map_err(ParameterError::WriteError)?;
                Ok(val.len() * 8)
            },
        });

        set_param_matches.extend(quote! {
            #hash => {
                let bytes = buffer.get_bits(64).to_be_bytes();
                #set_conversion
                true
            },
        });
    }

    quote! {
        impl PusParameters for #name {
            fn get_parameter_as_be_bytes(
                &self,
                hash: u32,
                writer: &mut BitWriter,
            ) -> Result<usize, ParameterError> {
                match hash {
                    #get_param_matches
                    _ => Err(ParameterError::UnknownParameter(hash)),
                }
            }

            fn set_parameter_from_be_bytes(&mut self, hash: u32, buffer: &mut BitBuffer) -> bool {
                match hash {
                    #set_param_matches
                    _ => false,
                }
            }

            fn get_parameter_size(&self, _hash: u32) -> Option<usize> {
                None // Deprecated function
            }
        }
    }
}
