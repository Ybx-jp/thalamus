# thalamus-console

Rooms and the console for [thalamus](https://github.com/Ybx-jp/thalamus): pinned
sessions opened as tmux windows, rooms that partition which sessions can see each other,
messages delivered between them, and a browser surface over all of it that works from a
phone.

Installing it adds:

- `thalamus spawn`: open a pinned session in a tmux window;
- `thalamus room`: list, show and create rooms;
- `thalamus dispatch`: deliver a message to a room's live members, refusing any that is
  waiting on a prompt;
- `thalamus ceremony`: the ledger of a room's occasions;
- `thalamus console`: the browser surface;
- `--room` on `thalamus pin`. Inside tmux, `thalamus pin` then opens its session in a
  new window rather than taking over the terminal;
- `--by-occasion` on `thalamus eval cost`;
- the room-member rows of `thalamus contract check --capabilities`.

It needs tmux on the PATH. It depends on `thalamus-memory` and nothing else from
thalamus, and registers through the `thalamus` entry-point group.

`pip install thalamus-console` installs it with the core it needs, or `uv tool install
thalamus-memory --with thalamus-console`. In a checkout of the repository, `uv sync`
installs it into the development environment. See [docs/console.md](https://github.com/Ybx-jp/thalamus/blob/master/docs/console.md) for running it.
