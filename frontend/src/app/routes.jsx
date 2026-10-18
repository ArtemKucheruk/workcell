import { NotFound } from '../components/NotFound.jsx'
import { BoardPage } from '../pages/board/BoardPage.jsx'
import { DashboardPage } from '../pages/dashboard/DashboardPage.jsx'
import { ReviewPage } from '../pages/review/ReviewPage.jsx'
import { TaskPage } from '../pages/task/TaskPage.jsx'
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
      { path: '/tasks/:id', element: <TaskPage /> },
      { path: '/tasks/:id/review', element: <ReviewPage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
]
