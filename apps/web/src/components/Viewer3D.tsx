"use client";

import type { Solid } from "@homeworking/api-client";
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import { toneColor } from "@/lib/tones";

type Props = {
  solids: Solid[];
  highlight: number | null;
  onHover: (position: number | null) => void;
  label: string;
};

// Model space: x right, y back, z up (mm). three.js: y up, camera looks along -z.
function toThree([x, y, z]: readonly [number, number, number]): THREE.Vector3 {
  return new THREE.Vector3(x, z, -y);
}

function partMaterial(solid: Solid): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    color: toneColor(solid.tone),
    roughness: 0.85,
    metalness: solid.tone === "steel" ? 0.6 : 0,
  });
}

function withEdges(mesh: THREE.Mesh): THREE.Mesh {
  // Only real edges (crease > 20°): triangulated faces of contours stay clean.
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(mesh.geometry, 20),
    new THREE.LineBasicMaterial({ color: 0x374151, transparent: true, opacity: 0.55 }),
  );
  mesh.add(edges);
  return mesh;
}

/** Shaped, cut or angled parts: the engine sends a triangle mesh in model coordinates. */
function buildMesh(solid: Solid, mesh: NonNullable<Solid["mesh"]>): THREE.Group {
  const positions = new Float32Array(mesh.triangles.length * 9);
  mesh.triangles.forEach((triangle, t) => {
    triangle.forEach((index, k) => {
      const p = toThree(mesh.vertices[index] as [number, number, number]);
      positions.set([p.x, p.y, p.z], t * 9 + k * 3);
    });
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  // Not indexed: every face keeps its own normal (flat shading at sharp edges).
  geometry.computeVertexNormals();
  const part = new THREE.Mesh(geometry, partMaterial(solid));
  part.userData.position = solid.position;
  const group = new THREE.Group();
  group.add(withEdges(part));
  return group;
}

function buildPart(solid: Solid): THREE.Group {
  if (solid.mesh) return buildMesh(solid, solid.mesh);
  const [sx, sy, sz] = solid.size;
  const pivot = new THREE.Group();
  pivot.position.copy(toThree(solid.at));
  if (solid.rotation) {
    const angle = THREE.MathUtils.degToRad(solid.rotation.deg);
    if (solid.rotation.axis === "x") pivot.rotation.x = angle;
    if (solid.rotation.axis === "y") pivot.rotation.z = -angle;
    if (solid.rotation.axis === "z") pivot.rotation.y = angle;
  }
  const geometry = new THREE.BoxGeometry(sx, sz, sy);
  const mesh = new THREE.Mesh(geometry, partMaterial(solid));
  mesh.position.set(sx / 2, sz / 2, -sy / 2);
  mesh.userData.position = solid.position;
  pivot.add(withEdges(mesh));
  return pivot;
}

export default function Viewer3D({ solids, highlight, onHover, label }: Props) {
  const mount = useRef<HTMLDivElement>(null);
  const applyHighlight = useRef<(position: number | null) => void>(() => {});
  const hoverRef = useRef(onHover);

  useEffect(() => {
    hoverRef.current = onHover;
  }, [onHover]);

  useEffect(() => {
    const host = mount.current;
    if (!host) return;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    host.appendChild(renderer.domElement);
    renderer.domElement.setAttribute("aria-hidden", "true");

    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xffffff, 0xb7a58f, 1.6));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(1, 2, 1.4);
    scene.add(sun);

    const model = new THREE.Group();
    const meshes: THREE.Mesh[] = [];
    for (const solid of solids) {
      const part = buildPart(solid);
      model.add(part);
      part.traverse((o) => {
        if (o instanceof THREE.Mesh) meshes.push(o);
      });
    }
    scene.add(model);

    const box = new THREE.Box3().setFromObject(model);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const radius = Math.max(size.length() / 2, 1);
    // The floor follows the theme (a light disc on a dark stage glares).
    const floor = getComputedStyle(host).getPropertyValue("--surface-muted").trim() || "#e2e5e0";
    const ground = new THREE.Mesh(
      new THREE.CircleGeometry(radius * 1.6, 48),
      new THREE.MeshBasicMaterial({
        color: new THREE.Color(floor),
        transparent: true,
        opacity: 0.6,
      }),
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(center.x, box.min.y - 1, center.z);
    scene.add(ground);

    const camera = new THREE.PerspectiveCamera(35, 1, radius / 50, radius * 20);
    const direction = new THREE.Vector3(1.1, 0.8, 1.5).normalize();
    camera.position.copy(center).addScaledVector(direction, radius * 3.2);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.copy(center);
    controls.update();
    controls.enableDamping = false;
    controls.maxPolarAngle = Math.PI * 0.55;

    const draw = () => renderer.render(scene, camera);
    controls.addEventListener("change", draw);
    applyHighlight.current = (highlight) => {
      for (const mesh of meshes) {
        const material = mesh.material as THREE.MeshStandardMaterial;
        const active = highlight !== null && mesh.userData.position === highlight;
        const dimmed = highlight !== null && !active;
        material.emissive.set(active ? 0x1e4e8c : 0x000000);
        material.emissiveIntensity = active ? 0.35 : 0;
        material.transparent = dimmed;
        material.opacity = dimmed ? 0.45 : 1;
      }
      draw();
    };

    const resize = () => {
      const width = host.clientWidth;
      const height = host.clientHeight;
      renderer.setSize(width, height, false);
      renderer.domElement.style.width = "100%";
      renderer.domElement.style.height = "100%";
      camera.aspect = width / Math.max(height, 1);
      camera.updateProjectionMatrix();
      draw();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const onMove = (event: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.set(
        ((event.clientX - rect.left) / rect.width) * 2 - 1,
        -((event.clientY - rect.top) / rect.height) * 2 + 1,
      );
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(meshes, false)[0];
      hoverRef.current(hit ? (hit.object.userData.position as number) : null);
    };
    const onLeave = () => hoverRef.current(null);
    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("pointerleave", onLeave);

    return () => {
      observer.disconnect();
      controls.dispose();
      renderer.domElement.removeEventListener("pointermove", onMove);
      renderer.domElement.removeEventListener("pointerleave", onLeave);
      scene.traverse((o) => {
        if (o instanceof THREE.Mesh || o instanceof THREE.LineSegments) {
          o.geometry.dispose();
          const materials = Array.isArray(o.material) ? o.material : [o.material];
          materials.forEach((m: THREE.Material) => m.dispose());
        }
      });
      renderer.dispose();
      host.removeChild(renderer.domElement);
    };
  }, [solids]);

  useEffect(() => {
    applyHighlight.current(highlight);
  }, [highlight, solids]);

  return (
    <div
      ref={mount}
      role="img"
      aria-label={label}
      className="h-full w-full cursor-grab touch-none active:cursor-grabbing"
      data-testid="viewer-3d"
    />
  );
}
