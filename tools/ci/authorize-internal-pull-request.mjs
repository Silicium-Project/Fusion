import { authorizeInternalPullRequest } from '../lib/github-authorization.mjs';

const result = await authorizeInternalPullRequest({
  repository: process.env.GITHUB_REPOSITORY,
  number: process.env.PULL_NUMBER,
  token: process.env.GH_TOKEN,
});

console.log(JSON.stringify(result));
