import { createBrowserRouter } from "react-router";

import { Layout } from "@/routes/Layout";
import { DatenschutzPage } from "@/routes/DatenschutzPage";
import { HomePage } from "@/routes/HomePage";
import { ImpressumPage } from "@/routes/ImpressumPage";
import { NotFoundPage } from "@/routes/NotFoundPage";
import { ProjectPage } from "@/routes/ProjectPage";
import { ProjectsPage } from "@/routes/ProjectsPage";

export const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <HomePage /> },
      { path: "/projects", element: <ProjectsPage /> },
      { path: "/projects/:id", element: <ProjectPage /> },
      { path: "/impressum", element: <ImpressumPage /> },
      { path: "/datenschutz", element: <DatenschutzPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
