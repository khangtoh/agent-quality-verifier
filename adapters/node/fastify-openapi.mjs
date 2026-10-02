// A5 adapter for Fastify with @fastify/swagger: prints the OpenAPI document Fastify
// generates from the routes it actually registered. Run with tsx for TypeScript apps:
//   npx tsx fastify-openapi.mjs <module relative to cwd> [factory export name, default createApp]
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const mod = await import(pathToFileURL(resolve(process.argv[2])).href);
const app = await mod[process.argv[3] || "createApp"]();
await app.ready();
console.log(JSON.stringify(app.swagger()));
await app.close();
