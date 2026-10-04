import { useEffect, useRef, useState } from "react";
import type { MapRecord } from "../lib/types";

const hashText = (value: string) => {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = Math.imul(31, hash) + value.charCodeAt(index);
  }
  return Math.abs(hash);
};

const seeded = (seed: number) => {
  let value = seed || 1;
  return () => {
    value = (value * 1664525 + 1013904223) >>> 0;
    return value / 2 ** 32;
  };
};

export function MapPreviewCanvas({ map }: { map: MapRecord }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [imageFailed, setImageFailed] = useState(false);

  useEffect(() => {
    setImageFailed(false);
  }, [map.id]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const size = 640;
    const context = canvas.getContext("2d");
    if (!context) return;

    const random = seeded(hashText(map.id));
    context.clearRect(0, 0, size, size);

    const gradient = context.createLinearGradient(0, 0, size, size);
    gradient.addColorStop(0, "#304d43");
    gradient.addColorStop(0.52, "#53665e");
    gradient.addColorStop(1, "#213b56");
    context.fillStyle = gradient;
    context.fillRect(0, 0, size, size);

    const waterBias = random();
    context.globalAlpha = 0.8;
    context.fillStyle = waterBias > 0.55 ? "#315f7a" : "#324e66";
    for (let index = 0; index < 7; index += 1) {
      const x = random() * size;
      const y = random() * size;
      const radiusX = 90 + random() * 180;
      const radiusY = 60 + random() * 160;
      context.beginPath();
      context.ellipse(x, y, radiusX, radiusY, random() * Math.PI, 0, Math.PI * 2);
      context.fill();
    }

    context.globalAlpha = 0.3;
    context.strokeStyle = "#e8dfb6";
    context.lineWidth = 2;
    for (let line = 0; line < 12; line += 1) {
      context.beginPath();
      for (let step = 0; step <= 24; step += 1) {
        const x = (step / 24) * size;
        const y =
          line * 54 +
          Math.sin(step * 0.7 + random() * 4) * (12 + random() * 16) +
          random() * 18;
        if (step === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      }
      context.stroke();
    }

    const players = Math.max(2, Math.min(map.playerCount ?? 6, 16));
    context.globalAlpha = 1;
    for (let index = 0; index < players; index += 1) {
      const angle = (index / players) * Math.PI * 2 + random() * 0.3;
      const radius = 190 + random() * 70;
      const x = size / 2 + Math.cos(angle) * radius;
      const y = size / 2 + Math.sin(angle) * radius;
      context.fillStyle = "#f2d36b";
      context.beginPath();
      context.arc(x, y, 11, 0, Math.PI * 2);
      context.fill();
      context.strokeStyle = "#1d241f";
      context.lineWidth = 3;
      context.stroke();
    }

    context.globalAlpha = 0.9;
    context.fillStyle = "#8ee4a7";
    for (let index = 0; index < 18; index += 1) {
      const x = 70 + random() * (size - 140);
      const y = 70 + random() * (size - 140);
      context.fillRect(x - 4, y - 4, 8, 8);
    }
  }, [map]);

  if (map.previewUrl && !imageFailed) {
    return <img className="map-preview" src={map.previewUrl} alt="" onError={() => setImageFailed(true)} />;
  }

  return <canvas ref={canvasRef} className="map-preview" width="640" height="640" aria-hidden />;
}
