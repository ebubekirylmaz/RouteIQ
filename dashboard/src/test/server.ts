import { setupServer } from "msw/node";

/** Network stand-in for the tests. Each test adds its own handlers with `server.use(...)`. */
export const server = setupServer();
