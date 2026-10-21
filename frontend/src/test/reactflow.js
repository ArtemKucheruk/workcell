// 051: React Flow's documented jsdom mocks (reactflow.dev, "Testing"), for the designer's tests only. jsdom lays nothing
// out, so React Flow would measure no node and draw no edge without them.

class ResizeObserver {
  constructor(callback) {
    this.callback = callback
  }
  // 12.12's pan-zoom also reads contentRect, which the documented mock leaves out
  observe(target) {
    this.callback([{ target, contentRect: { width: target.offsetWidth, height: target.offsetHeight } }], this)
  }
  unobserve() {}
  disconnect() {}
}

class DOMMatrixReadOnly {
  constructor(transform) {
    const scale = transform?.match(/scale\(([1-9.])\)/)?.[1]
    this.m22 = scale !== undefined ? +scale : 1
  }
}

globalThis.ResizeObserver = ResizeObserver
globalThis.DOMMatrixReadOnly = DOMMatrixReadOnly
Object.defineProperties(HTMLElement.prototype, {
  offsetHeight: { configurable: true, get() { return parseFloat(this.style.height) || 1 } },
  offsetWidth: { configurable: true, get() { return parseFloat(this.style.width) || 1 } },
})
SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 0, height: 0 })
