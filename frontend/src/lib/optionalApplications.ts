import type { OptionalApplication, OptionalChoice, OptionalChoiceInput, OptionalColor, OrderItem, Product } from '../types'
import { optionalBrand } from './optionalGroups'
import { optionalName, optionalCategoryLabel } from './optionalLabels'

export interface ProductApplication {
  application: OptionalApplication
  componentName: string | null
}

export interface RequiredApplicationProgress {
  filled: number
  total: number
  missing: number
}

/** Valor da opção "Customizado" no seletor; não é id de opcional. */
export const CUSTOM_OPTION = '__custom__'
/** Valor da escolha customizada no seletor antigo (opt_categories). Pedidos
 *  anteriores podem trazer "Customizado: <texto>", da época da caixa de texto. */
export const CUSTOM_LEGACY_VALUE = 'Customizado'

/** Valor da opção "Tecido fornecido" no seletor; não é id de opcional. */
export const SUPPLIED_FABRIC_OPTION = '__supplied_fabric__'
/** Categoria de tecidos IBTW de Portugal: só nas aplicações dela existe TECIDO FORNECIDO. */
export const SUPPLIED_FABRIC_CATEGORY = 'TECIDOS_IBTW'

export function suppliedFabricLabel(english: boolean): string {
  return english ? 'SUPPLIED FABRIC' : 'TECIDO FORNECIDO'
}

/** TECIDO FORNECIDO é marcado por supplied_fabric (sem optional_id nem custom_text). */
export function isSuppliedChoice(choice: Pick<OptionalChoiceInput, 'supplied_fabric'>): boolean {
  return choice.supplied_fabric === true
}

/** A opção só aparece em produto EU com dados importados, na aplicação de tecidos IBTW. */
export function offersSuppliedFabric(product: Product, application: Pick<OptionalApplication, 'category_code'>): boolean {
  return product.market_code === 'EU'
    && product.supplied_fabric != null
    && application.category_code === SUPPLIED_FABRIC_CATEGORY
}

/** Texto gravado em opt_categories quando o seletor antigo escolhe TECIDO FORNECIDO. */
export const LEGACY_SUPPLIED_FABRIC_VALUE = 'TECIDO FORNECIDO'

/** No seletor antigo (produto sem aplicação) a escolha é o próprio texto, guardado em opt_categories. */
export function isLegacySuppliedFabric(value: string | undefined | null): boolean {
  return (value ?? '').trim().toUpperCase() === 'TECIDO FORNECIDO'
}

/** O seletor antigo da categoria de tecidos IBTW oferece a opção em produto EU com dados. */
export function offersSuppliedFabricLegacy(product: Product, categoryCode: string): boolean {
  return product.market_code === 'EU' && product.supplied_fabric != null && categoryCode === SUPPLIED_FABRIC_CATEGORY
}

export interface SuppliedFabricLine {
  /** Metragem linear de tecido (coluna "MTS TECIDO" da planilha). */
  meters: number
  /** Preço unitário "sem tecido" da tabela do orçamento; null se a tabela não é visível. */
  price: number | null
}

/** Dado do tecido fornecido quando alguma aplicação do produto está nesta opção; só prévia, o servidor recalcula. */
export function suppliedFabricLine(
  product: Product,
  choices: Pick<OptionalChoiceInput, 'application_id' | 'supplied_fabric'>[],
  priceProfile: string | undefined,
  legacySelections: Partial<Record<string, string>> = {},
): SuppliedFabricLine | null {
  const fabric = product.supplied_fabric
  if (!fabric) return null
  const offered = new Set(productApplications(product)
    .filter(entry => offersSuppliedFabric(product, entry.application))
    .map(entry => entry.application.id))
  const legacy = offersSuppliedFabricLegacy(product, SUPPLIED_FABRIC_CATEGORY)
    && isLegacySuppliedFabric(legacySelections[SUPPLIED_FABRIC_CATEGORY])
  if (!legacy && !choices.some(choice => isSuppliedChoice(choice) && offered.has(choice.application_id))) return null
  const price = fabric.prices?.[priceProfile ?? 'lojista']
  return { meters: Number(fabric.linear_meters), price: price == null ? null : Number(price) }
}

/** 13,2 m (pt-PT) / 13.2 m (en-GB). */
export function formatFabricMeters(meters: number | string, english: boolean): string {
  return `${new Intl.NumberFormat(english ? 'en-GB' : 'pt-PT', { maximumFractionDigits: 2 }).format(Number(meters))} m`
}

/**
 * Aplica a escolha de uma aplicação. TECIDO FORNECIDO vale para todos os tecidos
 * IBTW do produto (o preço da planilha é "sem tecido"): escolher numa aplicação
 * marca as outras, e trocar por outra opção desmarca as irmãs.
 */
export function nextApplicationChoices(
  product: Product,
  choices: OptionalChoiceInput[],
  applicationId: string,
  choice: OptionalChoiceInput | null,
): OptionalChoiceInput[] {
  const fabricIds = productApplications(product)
    .filter(entry => offersSuppliedFabric(product, entry.application))
    .map(entry => entry.application.id)
  const wasSupplied = choices.some(candidate => candidate.application_id === applicationId && isSuppliedChoice(candidate))
  let next = [...choices.filter(candidate => candidate.application_id !== applicationId), ...(choice ? [choice] : [])]
  if (choice && isSuppliedChoice(choice) && fabricIds.includes(applicationId)) {
    next = next.filter(candidate => !fabricIds.includes(candidate.application_id) || candidate.application_id === applicationId)
    next.push(...fabricIds.filter(id => id !== applicationId).map(id => ({ application_id: id, supplied_fabric: true })))
  } else if (wasSupplied) {
    next = next.filter(candidate => !(isSuppliedChoice(candidate) && fabricIds.includes(candidate.application_id)))
  }
  return next
}

/** "Customizado" existe só em Portugal; no Brasil o pedido usa apenas opcionais do cadastro. */
export function allowsCustomOption(market: 'BR' | 'EU'): boolean {
  return market === 'EU'
}

/** Acabamento ILYA não é personalizado: seletor com algum opcional ILYA não oferece "Customizado". */
export function allowsCustomFor(options: Pick<OptionalColor, 'brand'>[]): boolean {
  return !options.some(option => optionalBrand(option) === 'ILYA')
}

export function customOptionLabel(english: boolean): string {
  return english ? 'Custom' : 'Customizado'
}

/** Customizado é marcado por custom_text presente: vazio na escolha nova, com texto em pedidos anteriores. */
export function isCustomChoice(choice: Pick<OptionalChoiceInput, 'custom_text'>): boolean {
  return choice.custom_text != null
}

export function isLegacyCustom(value: string | undefined): boolean {
  return value === CUSTOM_LEGACY_VALUE || Boolean(value?.startsWith(`${CUSTOM_LEGACY_VALUE}:`))
}

function customValue(text: string | null | undefined, english: boolean): string {
  return text ? `${customOptionLabel(english)}: ${text}` : customOptionLabel(english)
}

export function choiceValue(choice: Pick<OptionalChoice, 'optional_name' | 'custom_text' | 'supplied_fabric'>, english: boolean): string {
  if (isSuppliedChoice(choice)) return suppliedFabricLabel(english)
  return isCustomChoice(choice) ? customValue(choice.custom_text, english) : optionalName(choice.optional_name, english)
}

function legacyValue(value: string, english: boolean): string {
  if (isLegacySuppliedFabric(value)) return suppliedFabricLabel(english)
  if (!isLegacyCustom(value)) return optionalName(value, english)
  return customValue(value.slice(CUSTOM_LEGACY_VALUE.length).replace(/^:\s*/, ''), english)
}

export function productApplications(product: Product): ProductApplication[] {
  return [
    ...(product.optional_applications ?? []).map(application => ({ application, componentName: null })),
    ...product.components.flatMap(component => (component.optional_applications ?? []).map(application => ({ application, componentName: component.description }))),
  ].sort((a, b) => a.application.display_order - b.application.display_order || a.application.id.localeCompare(b.application.id))
}

export function applicationName(application: Pick<OptionalApplication, 'name' | 'name_en'>, english: boolean): string {
  return english && application.name_en?.trim() ? application.name_en : application.name
}

export function allowedForApplication(application: OptionalApplication, allOptionals: OptionalColor[]): OptionalColor[] {
  return application.allow_all
    ? allOptionals.filter(option => option.category === application.category_code)
    : application.allowed_optionals
}

export function requiredApplicationProgress(
  product: Product,
  choices: OptionalChoiceInput[],
  allOptionals: OptionalColor[],
): RequiredApplicationProgress {
  const required = productApplications(product).filter(entry => entry.application.required)
  const choicesByApplication = new Map(choices.map(choice => [choice.application_id, choice]))
  const filled = required.filter(({ application }) => {
    const choice = choicesByApplication.get(application.id)
    if (!choice) return false
    if (isSuppliedChoice(choice)) return offersSuppliedFabric(product, application)
    const options = allowedForApplication(application, allOptionals)
    if (isCustomChoice(choice)) return allowsCustomFor(options)
    return options.some(option => option.id === choice.optional_id)
  }).length
  return { filled, total: required.length, missing: required.length - filled }
}

export function validateApplicationChoices(
  product: Product,
  choices: OptionalChoiceInput[],
  allOptionals: OptionalColor[],
  requireCompleteSelection = false,
  legacySelections: Partial<Record<string, string>> = {},
  /** Portugal salva o orçamento incompleto; a exigência vale ao finalizar. */
  allowIncomplete = false,
): string[] {
  const applications = productApplications(product).map(entry => entry.application)
  const byId = new Map(applications.map(application => [application.id, application]))
  const errors: string[] = []
  const applicationCategoryCodes = new Set(applications.map(application => application.category_code))
  const configuredLegacyCategoryCodes = new Set<string>()
  for (const optional of product.optionals ?? []) {
    configuredLegacyCategoryCodes.add(optional.category)
  }
  for (const raw of (product.all_optionals_categories ?? '').split(',')) {
    const code = raw.trim()
    if (code) configuredLegacyCategoryCodes.add(code)
  }
  for (const code of applicationCategoryCodes) {
    configuredLegacyCategoryCodes.delete(code)
  }
  const seenApplications = new Set<string>()
  const used = new Map<string, OptionalApplication>()
  for (const choice of choices) {
    const application = byId.get(choice.application_id)
    if (!application || seenApplications.has(choice.application_id)) { errors.push('Aplicação inválida ou repetida'); continue }
    seenApplications.add(choice.application_id)
    if (isSuppliedChoice(choice)) {
      if (!offersSuppliedFabric(product, application)) errors.push(`${application.name}: Tecido fornecido indisponível`)
      continue
    }
    const options = allowedForApplication(application, allOptionals)
    if (isCustomChoice(choice)) {
      if (!allowsCustomFor(options)) errors.push(`${application.name}: Customizado indisponível`)
      continue
    }
    if (!options.some(option => option.id === choice.optional_id)) {
      errors.push(`${application.name}: opção indisponível`)
      continue
    }
    const key = `${application.category_code}:${choice.optional_id}`
    const previous = used.get(key)
    if (previous && (!previous.allow_repeat || !application.allow_repeat)) errors.push(`${application.name}: escolha repetida`)
    used.set(key, application)
  }
  // O preço da planilha é "sem tecido": não mistura com outro tecido IBTW do mesmo produto.
  const fabricApplications = applications.filter(application => offersSuppliedFabric(product, application))
  const fabricChoices = choices.filter(choice => fabricApplications.some(application => application.id === choice.application_id))
  if (fabricChoices.some(isSuppliedChoice) && fabricChoices.some(choice => !isSuppliedChoice(choice))) {
    errors.push('Tecido fornecido deve valer para todos os tecidos IBTW do produto')
  }
  if (requireCompleteSelection && !allowIncomplete) {
    for (const application of applications) {
      if (!seenApplications.has(application.id)) errors.push(`${application.name}: escolha pendente`)
    }
    for (const categoryCode of configuredLegacyCategoryCodes) {
      if (!legacySelections[categoryCode]?.trim()) errors.push(`${categoryCode}: escolha pendente`)
    }
  }
  for (const application of applications) {
    if (!requireCompleteSelection && !allowIncomplete && application.required && !seenApplications.has(application.id)) errors.push(`${application.name}: escolha obrigatória`)
  }
  return errors
}

export function formatChoice(choice: OptionalChoice, english: boolean): string {
  const name = english && choice.application_name_en?.trim() ? choice.application_name_en : choice.application_name
  return `${choice.component_name ? `${choice.component_name} — ` : ''}${name}: ${choiceValue(choice, english)}`
}

export function orderOptionalSlots(
  item: Pick<OrderItem, 'opt_categories' | 'optional_choices'> & { supplied_fabric_meters?: number | string | null },
  english: boolean,
  categoryLabel: (code: string) => string,
): { label: string; value: string }[] {
  const meters = item.supplied_fabric_meters
  return [
    ...Object.entries(item.opt_categories ?? {}).map(([category, value]) => ({
      label: optionalCategoryLabel(categoryLabel(category), english), value: legacyValue(value, english),
    })),
    ...(item.optional_choices ?? []).map(choice => ({
      label: `${choice.component_name ? `${choice.component_name} — ` : ''}${english && choice.application_name_en ? choice.application_name_en : choice.application_name}`,
      value: choiceValue(choice, english),
    })),
    ...(meters == null ? [] : [{
      label: english ? 'Fabric required' : 'Tecido necessário',
      value: formatFabricMeters(meters, english),
    }]),
  ]
}
