import React, { memo, useEffect, useEffectEvent, useRef } from 'react';

interface Ripple {
  x: number;
  y: number;
  radius: number;
  alpha: number;
  velocity: number;
  lineWidth: number;
}

interface CanvasSize {
  width: number;
  height: number;
  dpr: number;
}

interface WaterLayer {
  spacing: number;
  amplitude: number;
  speed: number;
  lineWidth: number;
  color: string;
  alpha: number;
}

interface WaterBackgroundProps {
  variant?: 'screen' | 'table';
  className?: string;
}

const DEFAULT_CLASS_NAME = 'pointer-events-none absolute inset-0 z-0 h-full w-full';
const WATER_MOTION_PROFILE = {
  screen: {
    autoRippleInterval: 2200,
    dprCap: 1.15,
    frameInterval: 1000 / 22,
    highlightCount: 5,
    maxRipples: 18,
    resolutionScale: 0.72,
    rippleAlpha: 0.26,
    rippleLineScale: 2.1,
    rippleVelocity: 1.4,
    timeStep: 0.012,
    xStep: 30,
  },
  table: {
    autoRippleInterval: 2300,
    dprCap: 1.25,
    frameInterval: 1000 / 26,
    highlightCount: 4,
    maxRipples: 16,
    resolutionScale: 0.82,
    rippleAlpha: 0.18,
    rippleLineScale: 1.7,
    rippleVelocity: 1.1,
    timeStep: 0.015,
    xStep: 32,
  },
} as const;

function joinClassNames(...parts: Array<string | undefined>): string {
  return parts.filter(Boolean).join(' ');
}

export const WaterBackground = memo(function WaterBackground({
  variant = 'screen',
  className,
}: WaterBackgroundProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const ripplesRef = useRef<Ripple[]>([]);
  const sizeRef = useRef<CanvasSize>({ width: 0, height: 0, dpr: 1 });
  const timeRef = useRef(0);
  const autoRippleAtRef = useRef(0);
  const lastPointerRippleAtRef = useRef(0);
  const profile = WATER_MOTION_PROFILE[variant];

  const spawnRipple = useEffectEvent((x: number, y: number, strength = 1) => {
    const { width, height } = sizeRef.current;
    if (!width || !height) {
      return;
    }

    ripplesRef.current.push({
      x,
      y,
      radius: 10 + strength * 7,
      alpha: profile.rippleAlpha + strength * 0.16,
      velocity: profile.rippleVelocity + strength * 1.15,
      lineWidth: 1.2 + strength * profile.rippleLineScale,
    });

    if (ripplesRef.current.length > profile.maxRipples) {
      ripplesRef.current.splice(0, ripplesRef.current.length - profile.maxRipples);
    }
  });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) {
      return;
    }

    const setCanvasSize = (width: number, height: number) => {
      const dpr = Math.max(0.6, Math.min((window.devicePixelRatio || 1) * profile.resolutionScale, profile.dprCap));
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      sizeRef.current = { width, height, dpr };
    };

    const resize = () => {
      if (variant === 'table') {
        const bounds = canvas.parentElement?.getBoundingClientRect();
        setCanvasSize(Math.max(0, Math.floor(bounds?.width ?? 0)), Math.max(0, Math.floor(bounds?.height ?? 0)));
        return;
      }
      setCanvasSize(window.innerWidth, window.innerHeight);
    };

    const drawBackdropGlow = (width: number, height: number, time: number) => {
      if (variant === 'table') {
        const centerGlow = ctx.createRadialGradient(width * 0.52, height * 0.48, 0, width * 0.52, height * 0.48, width * 0.58);
        centerGlow.addColorStop(0, 'rgba(214, 255, 235, 0.24)');
        centerGlow.addColorStop(0.18, 'rgba(176, 255, 221, 0.18)');
        centerGlow.addColorStop(0.42, 'rgba(95, 229, 178, 0.1)');
        centerGlow.addColorStop(1, 'rgba(0, 0, 0, 0)');
        ctx.fillStyle = centerGlow;
        ctx.fillRect(0, 0, width, height);

        const sweepX = width * (0.06 + ((time * 0.028) % 1) * 0.88);
        const sweep = ctx.createRadialGradient(sweepX, height * 0.24, 0, sweepX, height * 0.24, width * 0.26);
        sweep.addColorStop(0, 'rgba(255, 255, 255, 0.12)');
        sweep.addColorStop(0.4, 'rgba(185, 255, 232, 0.075)');
        sweep.addColorStop(1, 'rgba(0, 0, 0, 0)');
        ctx.fillStyle = sweep;
        ctx.fillRect(0, 0, width, height);

        const vignette = ctx.createRadialGradient(width * 0.5, height * 0.48, width * 0.16, width * 0.5, height * 0.48, width * 0.72);
        vignette.addColorStop(0, 'rgba(0, 0, 0, 0)');
        vignette.addColorStop(0.62, 'rgba(2, 18, 10, 0.04)');
        vignette.addColorStop(0.86, 'rgba(2, 18, 10, 0.22)');
        vignette.addColorStop(1, 'rgba(1, 10, 6, 0.44)');
        ctx.fillStyle = vignette;
        ctx.fillRect(0, 0, width, height);

        const sideShade = ctx.createLinearGradient(0, 0, width, 0);
        sideShade.addColorStop(0, 'rgba(1, 10, 6, 0.34)');
        sideShade.addColorStop(0.12, 'rgba(1, 10, 6, 0.14)');
        sideShade.addColorStop(0.28, 'rgba(0, 0, 0, 0)');
        sideShade.addColorStop(0.72, 'rgba(0, 0, 0, 0)');
        sideShade.addColorStop(0.88, 'rgba(1, 10, 6, 0.14)');
        sideShade.addColorStop(1, 'rgba(1, 10, 6, 0.34)');
        ctx.fillStyle = sideShade;
        ctx.fillRect(0, 0, width, height);
        return;
      }

      const leftGlow = ctx.createRadialGradient(width * 0.18, height * 0.15, 0, width * 0.18, height * 0.15, width * 0.58);
      leftGlow.addColorStop(0, 'rgba(125, 255, 226, 0.18)');
      leftGlow.addColorStop(0.45, 'rgba(90, 210, 190, 0.08)');
      leftGlow.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = leftGlow;
      ctx.fillRect(0, 0, width, height);

      const rightGlow = ctx.createRadialGradient(width * 0.84, height * 0.82, 0, width * 0.84, height * 0.82, width * 0.64);
      rightGlow.addColorStop(0, 'rgba(118, 189, 255, 0.14)');
      rightGlow.addColorStop(0.4, 'rgba(78, 134, 255, 0.06)');
      rightGlow.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = rightGlow;
      ctx.fillRect(0, 0, width, height);
    };

    const drawWaterBands = (width: number, height: number, time: number) => {
      const layers: WaterLayer[] =
        variant === 'table'
          ? [
              { spacing: 58, amplitude: 8, speed: 0.94, lineWidth: 2.2, color: '197, 255, 238', alpha: 0.1 },
              { spacing: 104, amplitude: 14, speed: 0.58, lineWidth: 3.6, color: '255, 255, 255', alpha: 0.065 },
              { spacing: 156, amplitude: 18, speed: 0.34, lineWidth: 5.4, color: '129, 255, 211', alpha: 0.04 },
            ]
          : [
              { spacing: 84, amplitude: 12, speed: 0.72, lineWidth: 3.4, color: '128, 255, 220', alpha: 0.11 },
              { spacing: 124, amplitude: 18, speed: 0.44, lineWidth: 5.4, color: '255, 255, 255', alpha: 0.075 },
              { spacing: 176, amplitude: 24, speed: 0.24, lineWidth: 7.8, color: '118, 189, 255', alpha: 0.045 },
            ];

      for (const layer of layers) {
        ctx.strokeStyle = `rgba(${layer.color}, ${layer.alpha})`;
        ctx.lineWidth = layer.lineWidth;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';

        for (let baseY = -layer.spacing; baseY < height + layer.spacing; baseY += layer.spacing) {
          ctx.beginPath();
          for (let x = -40; x <= width + 40; x += profile.xStep) {
            const y =
              baseY +
              Math.sin(x * (variant === 'table' ? 0.0084 : 0.0058) + time * layer.speed + baseY * 0.011) * layer.amplitude +
              Math.cos(x * 0.0027 - time * (layer.speed + 0.08) + baseY * 0.004) * layer.amplitude * 0.35;

            if (x <= -40) {
              ctx.moveTo(x, y);
            } else {
              ctx.lineTo(x, y);
            }
          }
          ctx.stroke();
        }
      }
    };

    const drawDriftingHighlights = (width: number, height: number, time: number) => {
      const count = profile.highlightCount;
      for (let index = 0; index < count; index += 1) {
        const x = ((index * 0.17 + time * (variant === 'table' ? 0.024 : 0.018)) % 1) * width;
        const y = height * (variant === 'table' ? 0.18 + index * 0.13 : 0.12 + index * 0.11) + Math.sin(time * 0.9 + index) * 18;
        const radius = (variant === 'table' ? 90 : 110) + index * 14;
        const glow = ctx.createRadialGradient(x, y, 0, x, y, radius);
        glow.addColorStop(0, `rgba(255, 255, 255, ${variant === 'table' ? 0.09 : 0.12})`);
        glow.addColorStop(0.35, `rgba(160, 255, 231, ${variant === 'table' ? 0.05 : 0.06})`);
        glow.addColorStop(1, 'rgba(0, 0, 0, 0)');
        ctx.fillStyle = glow;
        ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2);
      }
    };

    const drawFlowSweeps = (width: number, height: number, time: number) => {
      if (variant !== 'table') {
        return;
      }

      const sweeps = [
        { widthRatio: 0.36, heightRatio: 0.12, yRatio: 0.22, speed: 0.022, alpha: 0.1 },
        { widthRatio: 0.48, heightRatio: 0.15, yRatio: 0.5, speed: 0.016, alpha: 0.075 },
      ];

      for (let index = 0; index < sweeps.length; index += 1) {
        const sweep = sweeps[index];
        const centerX = ((0.12 + index * 0.23 + time * sweep.speed) % 1.2) * width - width * 0.1;
        const centerY = height * sweep.yRatio + Math.sin(time * (0.72 + index * 0.08) + index) * 12;
        const radiusX = width * sweep.widthRatio;
        const radiusY = height * sweep.heightRatio;

        ctx.save();
        ctx.translate(centerX, centerY);
        ctx.scale(radiusX, radiusY);

        const glow = ctx.createRadialGradient(0, 0, 0, 0, 0, 1);
        glow.addColorStop(0, `rgba(255, 255, 255, ${sweep.alpha})`);
        glow.addColorStop(0.28, `rgba(212, 255, 235, ${sweep.alpha * 0.68})`);
        glow.addColorStop(0.6, 'rgba(140, 255, 219, 0.03)');
        glow.addColorStop(1, 'rgba(0, 0, 0, 0)');
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.ellipse(0, 0, 1, 1, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }
    };

    const drawRipples = () => {
      const ripples = ripplesRef.current;
      const limit = Math.max(sizeRef.current.width, sizeRef.current.height) * (variant === 'table' ? 0.32 : 0.45);

      for (let index = ripples.length - 1; index >= 0; index -= 1) {
        const ripple = ripples[index];

        ctx.beginPath();
        ctx.arc(ripple.x, ripple.y, ripple.radius, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(255, 255, 255, ${ripple.alpha})`;
        ctx.lineWidth = ripple.lineWidth;
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(ripple.x, ripple.y, ripple.radius * 0.62, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(123, 255, 223, ${ripple.alpha * 0.72})`;
        ctx.lineWidth = Math.max(1, ripple.lineWidth * 0.56);
        ctx.stroke();

        ripple.radius += ripple.velocity;
        ripple.alpha *= variant === 'table' ? 0.982 : 0.986;
        ripple.lineWidth *= 0.995;

        if (ripple.alpha < 0.015 || ripple.radius > limit) {
          ripples.splice(index, 1);
        }
      }
    };

    let animationFrameId = 0;
    let lastFrameAt = 0;
    let resizeObserver: ResizeObserver | null = null;
    let pageVisible = document.visibilityState !== 'hidden';

    const render = (now: number) => {
      if (!pageVisible) {
        animationFrameId = requestAnimationFrame(render);
        return;
      }

      if (!lastFrameAt) {
        lastFrameAt = now;
      }

      const elapsed = now - lastFrameAt;
      if (elapsed < profile.frameInterval) {
        animationFrameId = requestAnimationFrame(render);
        return;
      }

      lastFrameAt = now;
      const { width, height } = sizeRef.current;
      if (!width || !height) {
        animationFrameId = requestAnimationFrame(render);
        return;
      }

      ctx.clearRect(0, 0, width, height);
      timeRef.current += Math.min(elapsed, 64) / 16.6667 * profile.timeStep;

      drawBackdropGlow(width, height, timeRef.current);
      drawWaterBands(width, height, timeRef.current);
      drawDriftingHighlights(width, height, timeRef.current);
      drawFlowSweeps(width, height, timeRef.current);

      if (now - autoRippleAtRef.current > profile.autoRippleInterval) {
        autoRippleAtRef.current = now;
        spawnRipple(width * (0.18 + Math.random() * 0.64), height * (0.18 + Math.random() * 0.5), 0.48 + Math.random() * 0.36);
      }

      drawRipples();
      animationFrameId = requestAnimationFrame(render);
    };

    const handleVisibilityChange = () => {
      pageVisible = document.visibilityState !== 'hidden';
      if (pageVisible) {
        lastFrameAt = 0;
      }
    };

    const handlePointerMove = (event: PointerEvent) => {
      const now = performance.now();
      if (now - lastPointerRippleAtRef.current < 160) {
        return;
      }

      if (variant === 'table') {
        const bounds = canvas.getBoundingClientRect();
        if (
          event.clientX < bounds.left ||
          event.clientX > bounds.right ||
          event.clientY < bounds.top ||
          event.clientY > bounds.bottom
        ) {
          return;
        }
        lastPointerRippleAtRef.current = now;
        spawnRipple(event.clientX - bounds.left, event.clientY - bounds.top, 0.32);
        return;
      }

      lastPointerRippleAtRef.current = now;
      spawnRipple(event.clientX, event.clientY, 0.38);
    };

    const handlePointerDown = (event: PointerEvent) => {
      if (variant === 'table') {
        const bounds = canvas.getBoundingClientRect();
        if (
          event.clientX < bounds.left ||
          event.clientX > bounds.right ||
          event.clientY < bounds.top ||
          event.clientY > bounds.bottom
        ) {
          return;
        }
        spawnRipple(event.clientX - bounds.left, event.clientY - bounds.top, 0.86);
        return;
      }

      spawnRipple(event.clientX, event.clientY, 1.1);
    };

    resize();
    if (variant === 'table') {
      spawnRipple(sizeRef.current.width * 0.32, sizeRef.current.height * 0.42, 0.72);
      spawnRipple(sizeRef.current.width * 0.72, sizeRef.current.height * 0.56, 0.64);
    } else {
      spawnRipple(sizeRef.current.width * 0.26, sizeRef.current.height * 0.28, 0.9);
      spawnRipple(sizeRef.current.width * 0.74, sizeRef.current.height * 0.68, 0.8);
    }
    animationFrameId = requestAnimationFrame(render);

    if (variant === 'table') {
      const target = canvas.parentElement;
      if (target && 'ResizeObserver' in window) {
        resizeObserver = new ResizeObserver(() => resize());
        resizeObserver.observe(target);
      } else {
        window.addEventListener('resize', resize);
      }
    } else {
      window.addEventListener('resize', resize);
    }

    document.addEventListener('visibilitychange', handleVisibilityChange);

    const pointerTarget: HTMLElement | Window = variant === 'table' ? canvas.parentElement ?? window : window;
    if (variant === 'table') {
      pointerTarget.addEventListener('pointermove', handlePointerMove, { passive: true });
    }
    pointerTarget.addEventListener('pointerdown', handlePointerDown, { passive: true });

    return () => {
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      if (variant === 'table') {
        pointerTarget.removeEventListener('pointermove', handlePointerMove);
      }
      pointerTarget.removeEventListener('pointerdown', handlePointerDown);
      resizeObserver?.disconnect();
      cancelAnimationFrame(animationFrameId);
    };
  }, [profile, spawnRipple, variant]);

  return <canvas ref={canvasRef} className={joinClassNames(DEFAULT_CLASS_NAME, className)} />;
});
