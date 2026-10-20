import { NotFound } from '../components/NotFound.jsx'
import { BoardPage } from '../pages/board/BoardPage.jsx'
import { CodePage } from '../pages/code/CodePage.jsx'
import { DashboardPage } from '../pages/dashboard/DashboardPage.jsx'
import { FctlDocsPage } from '../pages/docs/FctlDocsPage.jsx'
import { ReviewPage } from '../pages/review/ReviewPage.jsx'
import { SettingsPage } from '../pages/settings/SettingsPage.jsx'
import { TaskPage } from '../pages/task/TaskPage.jsx'
import { TranscriptPage } from '../pages/transcript/TranscriptPage.jsx'
import { WorkspacePage } from '../pages/workspace/WorkspacePage.jsx'
import { Layout } from './Layout.jsx'

// docs/data-model-and-api.md §6.4: the SPA's routes; anything else outside /api is the not-found page
export const routes = [
  {
    element: <Layout />,
    children: [
      { path: '/', element: <DashboardPage /> },
      { path: '/workspaces/:id', element: <WorkspacePage /> },
      { path: '/projects/:id', element: <BoardPage /> },
      { path: '/projects/:id/code', element: <CodePage /> },
      { path: '/tasks/:id', element: <TaskPage /> },
      { path: '/tasks/:id/review', element: <ReviewPage /> },
      { path: '/transcripts/:id', element: <TranscriptPage /> },
      { path: '/docs/fctl', element: <FctlDocsPage /> },
      { path: '/settings', element: <SettingsPage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
]
