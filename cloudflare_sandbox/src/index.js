// One sandbox for each WebSocket, following
// https://developers.cloudflare.com/sandbox/commands/open-a-terminal-in-the-browser/ without the terminal:
// the first message is a Python program, which is started in a new container. Every later message is
// written to its stdin and whatever it writes to stdout is sent back. Closing the socket destroys the container.
import { DurableObject } from 'cloudflare:workers'

export class Sandbox extends DurableObject {
  async fetch() {
    const container = this.ctx.container
    // 1 vCPU; the default, `lite`, has a sixteenth of one
    container.start({ image: container.images.python, instance: 'standard-2', enableInternet: false })

    const [client, server] = Object.values(new WebSocketPair())
    // accept() rather than the hibernation API, so this object and its container stay up while the socket is open
    server.accept()
    const encoder = new TextEncoder()
    let stdin
    // messages are handled one at a time, so nothing reaches stdin before the program has started
    let queue = Promise.resolve()

    const handle = async (data) => {
      if (stdin) {
        await stdin.write(encoder.encode(data))
        return
      }
      // exec() waits for the container to be ready
      const program = await container.exec(['python3', '-u', '-c', data], { stdin: 'pipe' })
      stdin = program.stdin.getWriter()
      void (async () => {
        const decoder = new TextDecoder()
        for await (const chunk of program.stdout) {
          server.send(decoder.decode(chunk, { stream: true }))
        }
        server.close(1000, `exit ${await program.exitCode}`)
      })().catch((e) => server.close(1011, String(e).slice(0, 100)))
    }

    server.addEventListener('message', (event) => {
      queue = queue.then(() => handle(event.data)).catch((e) => server.close(1011, String(e).slice(0, 100)))
    })
    server.addEventListener('close', () => {
      this.ctx.waitUntil(container.destroy().then(() => this.ctx.storage.deleteAll()))
    })
    return new Response(null, { status: 101, webSocket: client })
  }
}

export default {
  async fetch(request, env) {
    // without the secret set, nothing gets in
    if (!env.API_KEY || request.headers.get('Authorization') !== `Bearer ${env.API_KEY}`) {
      return new Response('unauthorised', { status: 401 })
    }
    if (request.headers.get('Upgrade') !== 'websocket') {
      return new Response('expected a WebSocket', { status: 426 })
    }
    // the path is the sandbox's name: a new name is a new Durable Object with a new container
    return env.SANDBOX.getByName(new URL(request.url).pathname.slice(1)).fetch(request)
  },
}
