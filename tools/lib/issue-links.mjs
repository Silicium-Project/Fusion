/** Explicit contribution links; an incidental URL or numeric prefix is not a dependency. */
import { issueRef } from './github.mjs';
export function referencedIssues(body) {
  return [
    ...new Set(
      [
        ...String(body ?? '').matchAll(
          /^Refs:[\t ]+(https:\/\/github\.com\/Silicium-Project\/(?:Workbench|Fusion|planning-private)\/issues\/[1-9][0-9]*)[\t ]*\r?$/gm,
        ),
      ].map((match) => issueRef(match[1]).url),
    ),
  ];
}
export const referencesIssue = (body, url) => referencedIssues(body).includes(issueRef(url).url);
