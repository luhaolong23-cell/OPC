const source = new EventSource(window.location.pathname.replace('/debug', '') + '/events');
source.onmessage = () => {};
