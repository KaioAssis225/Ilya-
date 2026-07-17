export interface ProductGroup {
  id: string
  name: string
  ipi: number
}

export interface ProductGroupCreate {
  name: string
  ipi: number
}

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

export interface ProductSetComponent {
  id: string
  description: string
  is_circular: boolean
  altura: number
  largura: number
  profundidade: number
  qty: number
  optionals: OptionalColor[]
}

export interface ProductSetComponentCreate {
  description: string
  is_circular: boolean
  altura: number
  largura: number
  profundidade: number
  qty: number
  optional_ids: string[]
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
  price_lojista: number
  price_corporativo: number
  observacao: string | null
  all_optionals_categories: string | null
  optionals: OptionalColor[]
  set_items: ProductSetItem[]
  components: ProductSetComponent[]
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
  price_lojista?: number
  price_corporativo?: number
  observacao?: string | null
  all_optionals_categories?: string | null
  optional_ids?: string[]
  set_items?: ProductSetItemCreate[]
  components?: ProductSetComponentCreate[]
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
  price_profile: 'lojista' | 'corporativo'
  max_discount: number
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
  price_profile?: 'lojista' | 'corporativo'
  max_discount?: number
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
  discount?: number
  opt_categories?: Record<string, string>
}

export interface OrderCreate {
  client_id: string
  rep_id?: string | null
  notes?: string | null
  items: OrderItemCreate[]
}

export interface OrderUpdate {
  rep_id?: string | null
  notes?: string | null
  items?: OrderItemCreate[]
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
  opt_categories: Record<string, string>
  qty: number
  unit_price: number
  discount: number
  ipi_rate: number
  ipi_value: number
  observacao: string | null
  created_at: string
  updated_at: string
}

export interface OrderHistory {
  id: string
  order_id: string
  user_id: string | null
  user: { id: string; full_name: string } | null
  action: string
  details: string | null
  created_at: string
}

export interface OrderSummaryItem {
  product_code: string
  qty: number
}

export interface OrderSummary {
  id: string
  code: string
  orc_id: string
  client_id: string
  client_name: string
  rep_id: string | null
  rep_name: string | null
  total_value: number
  total_with_ipi: number
  is_finalized: boolean
  is_cancelled: boolean
  items: OrderSummaryItem[]
  created_at: string
}

export interface Order {
  id: string
  code: string
  orc_id: string
  client_id: string
  rep_id: string | null
  total_value: number
  total_ipi: number
  total_with_ipi: number
  is_finalized: boolean
  is_cancelled: boolean
  external_code: string | null
  notes: string | null
  rep_signed?: boolean
  client_signed?: boolean
  rep_signature?: string | null
  client_signature?: string | null
  items: OrderItem[]
  history: OrderHistory[]
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

export interface PageResult<T> {
  items: T[]
  total: number
  hasMore: boolean
  pageSize: number
}
