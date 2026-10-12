"use client";
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";

export default function GraphicsDemo({ shader, fallback = false }: { shader: boolean; fallback?: boolean }) {
  const host = useRef<HTMLDivElement>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (fallback) return;
    const mount = host.current;
    if (!mount) return;
    let renderer: THREE.WebGLRenderer | undefined;
    let geometry: THREE.BufferGeometry | undefined;
    let material: THREE.Material | undefined;
    let observer: ResizeObserver | undefined;
    let frame = 0;
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    let redraw: () => void = () => {};
    const lost = (event: Event) => { event.preventDefault(); cancelAnimationFrame(frame); setError(true); };
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5));
      renderer.domElement.setAttribute("aria-label", shader ? "GLSL colour and glow demonstration" : "Three-dimensional particle network");
      mount.appendChild(renderer.domElement);
      renderer.domElement.addEventListener("webglcontextlost", lost);
      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(45, 1, .1, 100);
      camera.position.z = 4.2;
      const uniforms = { time: { value: 0 } };
      let object: THREE.Object3D;
      if (shader) {
        geometry = new THREE.PlaneGeometry(3.2, 3.2);
        material = new THREE.ShaderMaterial({
          uniforms, transparent: true,
          vertexShader: `varying vec2 uvPoint; void main(){ uvPoint=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }`,
          fragmentShader: `precision mediump float;
            varying vec2 uvPoint; uniform float time;
            void main(){
              float distanceFromCentre=length(uvPoint-0.5);
              float glow=exp(-distanceFromCentre*7.0);
              float rings=0.5+0.5*sin(distanceFromCentre*40.0-time*1.5);
              vec3 teal=vec3(0.35,0.9,0.75); vec3 violet=vec3(0.7,0.5,0.95);
              vec3 colour=mix(teal,violet,rings*0.5);
              gl_FragColor=vec4(colour,glow*(0.75+rings*0.25));
            }`,
        });
        object = new THREE.Mesh(geometry, material);
      } else {
        const positions: number[] = [], colours: number[] = [];
        const palette = [0x8ee9d0, 0x86bceb, 0xc4a9e4, 0xefd099];
        for (let i = 0; i < 180; i++) {
          const y = 1 - i / 179 * 2, r = Math.sqrt(1 - y * y), angle = i * 2.399963;
          positions.push(Math.cos(angle) * r, y, Math.sin(angle) * r);
          const colour = new THREE.Color(palette[i % 4]); colours.push(colour.r, colour.g, colour.b);
        }
        geometry = new THREE.BufferGeometry();
        geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
        geometry.setAttribute("color", new THREE.Float32BufferAttribute(colours, 3));
        material = new THREE.PointsMaterial({ size: .035, vertexColors: true, transparent: true, opacity: .9 });
        object = new THREE.Points(geometry, material);
      }
      scene.add(object);
      let previous = 0, elapsed = 0;
      const render = (time: number) => {
        if (!renderer || document.hidden) return;
        if (time - previous > 1000 / 30 || media.matches) {
          if (!media.matches) elapsed += previous ? Math.min(time - previous, 60) / 1000 : 0;
          previous = time;
          uniforms.time.value = elapsed;
          if (!shader) { object.rotation.y = elapsed * .16; object.rotation.x = .25; }
          renderer.render(scene, camera);
        }
        if (!media.matches) frame = requestAnimationFrame(render);
      };
      redraw = () => { cancelAnimationFrame(frame); previous = 0; if (!document.hidden) frame = requestAnimationFrame(render); };
      observer = new ResizeObserver(() => {
        const width = mount.clientWidth || 320;
        renderer?.setSize(width, 300); camera.aspect = width / 300; camera.updateProjectionMatrix(); redraw();
      });
      observer.observe(mount);
      media.addEventListener("change", redraw);
      document.addEventListener("visibilitychange", redraw);
      redraw();
    } catch { setError(true); }
    return () => {
      cancelAnimationFrame(frame); observer?.disconnect();
      media.removeEventListener("change", redraw); document.removeEventListener("visibilitychange", redraw);
      geometry?.dispose(); material?.dispose();
      if (renderer) { renderer.domElement.removeEventListener("webglcontextlost", lost); renderer.dispose(); renderer.forceContextLoss(); renderer.domElement.remove(); }
    };
  }, [shader, fallback]);
  return <div className="graphics-demo"><div ref={host} hidden={fallback || error} />{(fallback || error) && <div className="graphics-fallback"><div className="fallback-glow" /><p>{fallback ? "Fallback preview" : "3D graphics are unavailable in this browser."} This ordinary CSS glow keeps the example visible.</p></div>}</div>;
}
