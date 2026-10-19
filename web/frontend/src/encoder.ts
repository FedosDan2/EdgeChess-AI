/// <reference lib="webworker" />
const canvas = new OffscreenCanvas(960, 720);
const context = canvas.getContext("2d")!;
self.onmessage = async (event: MessageEvent) => {
  const { bitmap, id, captured, generation } = event.data;
  try {
    context.drawImage(bitmap, 0, 0, 960, 720);
    bitmap.close();
    const blob = await canvas.convertToBlob({
      type: "image/jpeg",
      quality: 0.88,
    });
    const jpeg = await blob.arrayBuffer();
    const packet = new ArrayBuffer(8 + jpeg.byteLength);
    new DataView(packet).setBigUint64(0, BigInt(id), false);
    new Uint8Array(packet, 8).set(new Uint8Array(jpeg));
    self.postMessage(
      { packet, id, captured, generation },
      { transfer: [packet] },
    );
  } catch (error) {
    bitmap.close();
    self.postMessage({ error: String(error), generation });
  }
};
