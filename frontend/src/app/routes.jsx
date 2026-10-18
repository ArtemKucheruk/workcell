import { NotFound } from '../components/NotFound.jsx'
import { DashboardPage } from '../pages/dashboard/DashboardPage.jsx'
import { WorkspacePage } from '../pages/workspace/WorkspacePage.jsx'
import { Layout } from './Layout.jsx'

// docs/data-model-and-api.md §6.4: the SPA's routes; anything else outside /api is the not-found page
export const routes = [
  {
    element: <Layout />,
    children: [
      { path: '/', element: <DashboardPage /> },
      { path: '/workspaces/:id', element: <WorkspacePage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
]
