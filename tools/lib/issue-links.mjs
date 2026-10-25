/** Explicit contribution links; an incidental URL or numeric prefix is not a dependency. */
export function referencedIssues(body) {
  return [
    ...new Set(
      [
        ...String(body ?? '').matchAll(
          /^Refs:[\t ]+(https:\/\/github\.com\/Silicium-Project\/(?:Fusion|planning-private)\/issues\/[1-9][0-9]*)[\t ]*\r?$/gm,
        ),
      ].map((match) => match[1]),
    ),
  ];
}
export const referencesIssue = (body, url) => referencedIssues(body).includes(url);
