// A5 adapter for Express 4: prints the routes an app serves as {"routes": ["GET /x", ...]}.
//   node express-routes.cjs <module relative to cwd> [factory export name, default createApp]
const path = require("path");
const mod = require(path.resolve(process.argv[2]));
const factory = mod[process.argv[3] || "createApp"];
const app = factory();
const routes = [];
for (const layer of (app._router && app._router.stack) || []) {
  if (!layer.route) continue;
  for (const [method, on] of Object.entries(layer.route.methods)) {
    if (on && method !== "_all") routes.push(`${method.toUpperCase()} ${layer.route.path}`);
  }
}
console.log(JSON.stringify({ routes }));
