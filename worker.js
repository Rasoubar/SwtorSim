export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/rotation_builder") {
      url.pathname = "/rotation_builder.html";
      return env.ASSETS.fetch(new Request(url.toString(), request));
    }
    return env.ASSETS.fetch(request);
  }
};
