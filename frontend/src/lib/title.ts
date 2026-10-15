import { useEffect } from "react";

export const DEFAULT_TITLE = "Homeworking – Was möchtest du bauen?";

/** Sets the document title for the current route (replaces Next.js `metadata.title`). */
export function useDocumentTitle(title: string = DEFAULT_TITLE) {
  useEffect(() => {
    document.title = title;
  }, [title]);
}
