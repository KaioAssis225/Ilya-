export interface OptionalColor {
  id: string
  category: string
  color_name: string
  photo_url: string | null
}

export interface OptionalColorCreate {
  category: string
  color_name: string
}

export interface OptionalColorUpdate extends Partial<OptionalColorCreate> {}

export interface ProductSetItem {
  product_code: string
  qty: number
  description: string
  photo_url: string | null
}

export interface ProductSetItemCreate {
  product_code: string
  qty: number
}

export interface Product {
  id: string
  product_code: string
  description: string
  type: string
  is_circular: boolean
  is_set: boolean
  altura: number
  largura: number
  profundidade: number
  price: number
  optionals: OptionalColor[]
  set_items: ProductSetItem[]
  photo_url: string | null
  created_at: string
  updated_at: string
}

export interface ProductCreate {
  product_code: string
  description: string
  type?: string
  is_circular: boolean
  is_set?: boolean
  altura: number
  largura: number
  profundidade: number
  price: number
  optional_ids?: string[]
  set_items?: ProductSetItemCreate[]
}

export interface ProductUpdate extends Partial<ProductCreate> {}

export interface Client {
  id: string
  name: string
  phone: string
  email: string
  cep: string
  numero: string | null
  address: string
  city: string
  state: string
  rep_id: string | null
  created_at: string
  updated_at: string
  has_user?: boolean
  user_validated?: boolean
}

export interface ClientCreate {
  name: string
  phone: string
  email: string
  cep: string
  numero?: string | null
  address: string
  city: string
  state: string
}

export interface ClientUpdate extends Partial<ClientCreate> {}

export interface Representative extends Omit<Client, 'id' | 'created_at' | 'updated_at'> {
  id: string
  created_at: string
  updated_at: string
  has_user?: boolean
}

export interface RepresentativeCreate extends ClientCreate {}
export interface RepresentativeUpdate extends Partial<RepresentativeCreate> {}

export interface OrderItemCreate {
  product_code: string
  qty: number
  opt_aluminio?: string | null
  opt_madeira?: string | null
  opt_tecido?: string | null
  opt_couro?: string | null
  opt_corda?: string | null
}

export interface OrderCreate {
  client_id: string
  rep_id?: string | null
  notes?: string | null
  items: OrderItemCreate[]
}

export interface OrderItem {
  id: string
  order_id: string
  product_code: string
  description: string
  is_circular: boolean
  altura: number
  largura: number
  profundidade: number
  opt_aluminio: string | null
  opt_madeira: string | null
  opt_tecido: string | null
  opt_couro: string | null
  opt_corda: string | null
  qty: number
  unit_price: number
  created_at: string
  updated_at: string
}

export interface Order {
  id: string
  code: string
  orc_id: string
  client_id: string
  rep_id: string | null
  total_value: number
  notes: string | null
  rep_signature: string | null
  client_signature: string | null
  items: OrderItem[]
  created_at: string
  updated_at: string
}

export interface ViaCepResponse {
  cep: string
  logradouro: string
  bairro: string
  localidade: string
  uf: string
  erro?: boolean
}
