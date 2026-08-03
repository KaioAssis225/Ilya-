// Assinaturas eletrônicas estão temporariamente desativadas.
// Para reativar a interface, configure VITE_ELECTRONIC_SIGNATURES_ENABLED=true
// no ambiente do frontend e gere um novo deploy.
export const ELECTRONIC_SIGNATURES_ENABLED =
  import.meta.env.VITE_ELECTRONIC_SIGNATURES_ENABLED === 'true'
