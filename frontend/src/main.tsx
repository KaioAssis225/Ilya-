import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Fontes self-hosted (LGPD L-01): mesmos family names do Google Fonts,
// servidas pelo próprio bundle em vez de fonts.googleapis.com
import '@fontsource/cormorant-garamond/400.css'
import '@fontsource/cormorant-garamond/500.css'
import '@fontsource/cormorant-garamond/600.css'
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
