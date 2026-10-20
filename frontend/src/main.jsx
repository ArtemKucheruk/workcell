import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { routes } from './app/routes.jsx'
// 040 Q4: self-hosted, so the app works offline on 127.0.0.1; Vite bundles the woff2 files
import '@fontsource-variable/ibm-plex-sans'
import '@fontsource-variable/jetbrains-mono'
import './index.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <RouterProvider router={createBrowserRouter(routes)} />
  </StrictMode>,
)
