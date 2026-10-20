import type { OptionalApplication, OptionalChoice, OptionalChoiceInput, OptionalColor, OrderItem, Product } from '../types'

export interface ProductApplication {
  application: OptionalApplication
  componentName: string | null
}

export interface RequiredApplicationProgress {
  filled: number
  total: number
  missing: number
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
  const choicesByApplication = new Map(choices.map(choice => [choice.application_id, choice.optional_id]))
  const filled = required.filter(({ application }) => {
    const selectedId = choicesByApplication.get(application.id)
    return Boolean(selectedId && allowedForApplication(application, allOptionals).some(option => option.id === selectedId))
  }).length
  return { filled, total: required.length, missing: required.length - filled }
}

export function validateApplicationChoices(product: Product, choices: OptionalChoiceInput[], allOptionals: OptionalColor[]): string[] {
  const applications = productApplications(product).map(entry => entry.application)
  const byId = new Map(applications.map(application => [application.id, application]))
  const errors: string[] = []
  const seenApplications = new Set<string>()
  const used = new Map<string, OptionalApplication>()
  for (const choice of choices) {
    const application = byId.get(choice.application_id)
    if (!application || seenApplications.has(choice.application_id)) { errors.push('Aplicação inválida ou repetida'); continue }
    seenApplications.add(choice.application_id)
    if (!allowedForApplication(application, allOptionals).some(option => option.id === choice.optional_id)) {
      errors.push(`${application.name}: opção indisponível`)
      continue
    }
    const key = `${application.category_code}:${choice.optional_id}`
    const previous = used.get(key)
    if (previous && (!previous.allow_repeat || !application.allow_repeat)) errors.push(`${application.name}: escolha repetida`)
    used.set(key, application)
  }
  for (const application of applications) {
    if (application.required && !seenApplications.has(application.id)) errors.push(`${application.name}: escolha obrigatória`)
  }
  return errors
}

export function formatChoice(choice: OptionalChoice, english: boolean): string {
  const name = english && choice.application_name_en?.trim() ? choice.application_name_en : choice.application_name
  return `${choice.component_name ? `${choice.component_name} — ` : ''}${name}: ${choice.optional_name}`
}

export function orderOptionalSlots(
  item: Pick<OrderItem, 'opt_categories' | 'optional_choices'>,
  english: boolean,
  categoryLabel: (code: string) => string,
): { label: string; value: string }[] {
  return [
    ...Object.entries(item.opt_categories ?? {}).map(([category, value]) => ({ label: categoryLabel(category), value })),
    ...(item.optional_choices ?? []).map(choice => ({
      label: `${choice.component_name ? `${choice.component_name} — ` : ''}${english && choice.application_name_en ? choice.application_name_en : choice.application_name}`,
      value: choice.optional_name,
    })),
  ]
}
