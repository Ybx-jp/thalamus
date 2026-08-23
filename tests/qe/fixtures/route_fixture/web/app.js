// The client half. Seven request literals in the file, six distinct routes.
//
// Relative and absolute are the same route: the console is served under a path-scoped
// mount, so the client addresses routes relatively while the server compares the
// absolute form. A query string is not part of the route, because the server splits it
// off before comparing. Delta is defined on the server with the operands the other way
// round, and must match all the same.
//
// One of the seven sits in a comment and nothing calls it. The matcher is text-level
// and does not know a comment from code, so it becomes a call and then an
// unmatched-call finding. That is characterized here, not endorsed: it is the shape a
// false accusation would take, and this fixture is where it stays visible.
//
// Removed in the rewrite, kept here as a note: `api/legacy`

async function load(id) {
  const a = await req(`api/alpha`);
  const b = await req("/api/alpha");
  const c = await req(`api/beta?pane=${id}`);
  const d = await req("api/gamma/leaf");
  const e = await req(`api/delta`);
  const f = await req(`api/ghost`);
  return [a, b, c, d, e, f];
}
