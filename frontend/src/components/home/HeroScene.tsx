import { Suspense, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Float, Sparkles, MeshDistortMaterial, Environment, Lightformer } from "@react-three/drei";
import * as THREE from "three";

// A fully procedural reflection environment — no HDR fetch, no external CDN.
// Renders a few emissive shapes into an offscreen cubemap so the gold metal
// gets real specular highlights without any network dependency.
function StudioEnvironment() {
  return (
    <Environment resolution={256}>
      <group>
        <Lightformer form="rect" intensity={6} color="#f8e3ab" scale={[8, 4, 1]} position={[6, 3, -3]} rotation={[0, -Math.PI / 3.2, 0]} />
        <Lightformer form="rect" intensity={3.5} color="#fff6e0" scale={[5, 5, 1]} position={[-4, 2, 4]} rotation={[0, Math.PI / 3, 0]} />
        <Lightformer form="ring" intensity={4} color="#ffffff" scale={5} position={[0, 5, 2]} rotation={[Math.PI / 2, 0, 0]} />
        <Lightformer form="rect" intensity={2} color="#3b4a6b" scale={[10, 6, 1]} position={[0, -6, -4]} rotation={[Math.PI / 2, 0, 0]} />
      </group>
    </Environment>
  );
}

function CoreGeometry() {
  const knotRef = useRef<THREE.Mesh>(null);
  const shellRef = useRef<THREE.Mesh>(null);
  const ringRef = useRef<THREE.Group>(null);

  useFrame((state, delta) => {
    if (knotRef.current) {
      knotRef.current.rotation.x += delta * 0.12;
      knotRef.current.rotation.y += delta * 0.18;
    }
    if (shellRef.current) {
      shellRef.current.rotation.y -= delta * 0.05;
    }
    if (ringRef.current) {
      ringRef.current.rotation.z += delta * 0.06;
      ringRef.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.15) * 0.25;
    }
  });

  return (
    <group position={[2.6, 0.1, -1]} scale={0.72}>
      <Float speed={1.4} rotationIntensity={0.5} floatIntensity={0.9}>
        <mesh ref={knotRef}>
          <torusKnotGeometry args={[1.35, 0.34, 220, 32, 2, 3]} />
          <MeshDistortMaterial
            color="#cba135"
            roughness={0.15}
            metalness={0.9}
            distort={0.18}
            speed={1.4}
            emissive="#7a5c1f"
            emissiveIntensity={0.25}
          />
        </mesh>
      </Float>

      <mesh ref={shellRef}>
        <icosahedronGeometry args={[2.7, 1]} />
        <meshBasicMaterial color="#e2c077" wireframe transparent opacity={0.08} />
      </mesh>

      <group ref={ringRef}>
        <mesh rotation={[Math.PI / 2.4, 0, 0]}>
          <torusGeometry args={[3.4, 0.006, 8, 180]} />
          <meshBasicMaterial color="#f1dca3" transparent opacity={0.35} />
        </mesh>
        <mesh rotation={[Math.PI / 1.6, 0.4, 0]}>
          <torusGeometry args={[3.9, 0.005, 8, 180]} />
          <meshBasicMaterial color="#cba135" transparent opacity={0.2} />
        </mesh>
      </group>
    </group>
  );
}

function Rig() {
  useFrame((state) => {
    const x = (state.pointer.x * Math.PI) / 40;
    const y = (state.pointer.y * Math.PI) / 40;
    state.camera.position.x += (x * 2 - state.camera.position.x) * 0.02;
    state.camera.position.y += (-y * 2 - state.camera.position.y) * 0.02;
    state.camera.lookAt(0, 0, 0);
  });
  return null;
}

export function HeroScene() {
  return (
    <Canvas
      dpr={[1, 1.75]}
      camera={{ position: [0, 0, 7.5], fov: 42 }}
      gl={{ antialias: true, alpha: true }}
      className="!absolute inset-0"
    >
      <Suspense fallback={null}>
        <ambientLight intensity={0.65} />
        <pointLight position={[6, 4, 6]} intensity={2.2} color="#f1dca3" />
        <pointLight position={[-6, -3, -4]} intensity={0.9} color="#3b4a6b" />
        <pointLight position={[-2, 5, 3]} intensity={1.1} color="#ffffff" />
        <CoreGeometry />
        <Sparkles count={90} scale={[9, 6, 6]} size={2.2} speed={0.25} color="#f1dca3" opacity={0.6} />
        <StudioEnvironment />
        <Rig />
      </Suspense>
    </Canvas>
  );
}
