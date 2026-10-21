import { NotFound } from '../components/NotFound.jsx'
import { BoardPage } from '../pages/board/BoardPage.jsx'
import { CodePage } from '../pages/code/CodePage.jsx'
import { ContextPage } from '../pages/context/ContextPage.jsx'
import { DashboardPage } from '../pages/dashboard/DashboardPage.jsx'
import { FactoriesPage } from '../pages/factories/FactoriesPage.jsx'
import { FactoryPage } from '../pages/factory/FactoryPage.jsx'
import { FctlDocsPage } from '../pages/docs/FctlDocsPage.jsx'
import { ProjectSettingsPage } from '../pages/project-settings/ProjectSettingsPage.jsx'
import { ReviewPage } from '../pages/review/ReviewPage.jsx'
import { ReviewsPage } from '../pages/reviews/ReviewsPage.jsx'
import { SettingsPage } from '../pages/settings/SettingsPage.jsx'
import { TaskPage } from '../pages/task/TaskPage.jsx'
import { TranscriptPage } from '../pages/transcript/TranscriptPage.jsx'
import { WorkspacePage } from '../pages/workspace/WorkspacePage.jsx'
import { WorkspaceSettingsPage } from '../pages/workspace-settings/WorkspaceSettingsPage.jsx'
import { Layout } from './Layout.jsx'

// docs/data-model-and-api.md §6.4: the SPA's routes; anything else outside /api is the not-found page
export const routes = [
  {
    // 041 Q14: `wide` routes drop main's max width
    element: <Layout />,
    children: [
      { path: '/', element: <DashboardPage /> },
      { path: '/workspaces/:id', element: <WorkspacePage /> },
      { path: '/workspaces/:id/settings', element: <WorkspaceSettingsPage /> }, // 049: a form page, not wide
      { path: '/projects/:id', element: <BoardPage />, handle: { wide: true } },
      { path: '/projects/:id/code', element: <CodePage />, handle: { wide: true } },
      // 042 FE37: lists and forms, so main keeps its max width
      { path: '/projects/:id/reviews', element: <ReviewsPage /> },
      { path: '/projects/:id/context', element: <ContextPage /> },
      { path: '/projects/:id/settings', element: <ProjectSettingsPage /> },
      { path: '/projects/:id/factories', element: <FactoriesPage /> }, // 051: a list, not wide
      { path: '/projects/:id/factories/:fid', element: <FactoryPage />, handle: { wide: true } },
      { path: '/tasks/:id', element: <TaskPage /> },
      { path: '/tasks/:id/review', element: <ReviewPage />, handle: { wide: true } },
      { path: '/transcripts/:id', element: <TranscriptPage /> },
      { path: '/docs/fctl', element: <FctlDocsPage /> },
      { path: '/settings', element: <SettingsPage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
]
