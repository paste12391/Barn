"""Endless runner 3D game built with Ursina.

This module defines a small but feature complete endless runner game
that can be launched directly with ``python -m game.main``.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from math import sin
from typing import List

from ursina import (  # type: ignore
    AmbientLight,
    Color,
    DirectionalLight,
    Entity,
    Sky,
    Text,
    Ursina,
    Vec3,
    camera,
    destroy,
    held_keys,
    lerp,
    raycast,
    time,
    window,
)


@dataclass
class TrackSegment:
    """A segment of the running track."""

    entity: Entity
    index: int


@dataclass
class Obstacle:
    """Obstacle wrapper to keep additional metadata."""

    entity: Entity
    lane: int


class RunnerGame:
    """Temple-run inspired endless runner built with Ursina.

    The player automatically runs forward and must avoid obstacles by
    moving between three lanes and jumping. Collision with an obstacle
    or falling off ends the run.
    """

    lanes = (-4, 0, 4)

    def __init__(self) -> None:
        self.app = Ursina(borderless=False)
        window.color = Color(0.08, 0.08, 0.15, 1)
        window.title = "Neon Drift Runner"
        window.exit_button.visible = False

        self.track_width = 14
        self.segment_length = 32
        self.segments: List[TrackSegment] = []
        self.obstacles: List[Obstacle] = []

        self.speed = 8.0
        self.acceleration = 0.35
        self.max_speed = 28.0
        self.lateral_speed = 9.0
        self.jump_force = 11.0
        self.gravity = 32.0
        self.vertical_velocity = 0.0
        self.is_running = False
        self.score = 0.0
        self.high_score = 0.0
        self.elapsed = 0.0

        self.player = Entity(
            model="cube",
            color=Color(0.3, 0.7, 0.9, 1),
            scale=(1.6, 2.2, 1.4),
            collider="box",
            position=Vec3(0, 1.1, -6),
        )
        self.player_hit_flash = Entity(
            parent=self.player,
            model="cube",
            scale=(1.01, 1.01, 1.01),
            color=Color(1, 0.2, 0.2, 0.0),
            enabled=False,
        )

        self.camera_pivot = Entity(parent=self.player, y=2.5, z=12)
        camera.parent = self.camera_pivot
        camera.position = (0, 3.4, -16)
        camera.rotation_x = 10

        self._setup_environment()
        self._setup_track()
        self._setup_ui()
        self._register_callbacks()

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------
    def _setup_environment(self) -> None:
        Sky(color=Color(0.02, 0.02, 0.05, 1))
        DirectionalLight(direction=(1, -1, -1), shadows=True)
        AmbientLight(color=Color(0.25, 0.25, 0.32, 1))

        self.music = None
        self.jump_sound = None
        self.crash_sound = None

    def _setup_track(self) -> None:
        track_parent = Entity()
        emissive_color = Color(0.1, 0.3, 0.7, 0.6)
        for i in range(8):
            entity = Entity(
                parent=track_parent,
                model="cube",
                scale=(self.track_width, 0.5, self.segment_length),
                collider="box",
                position=(0, -0.25, i * self.segment_length),
                color=Color(0.15, 0.15, 0.18, 1),
                texture="white_cube",
                texture_scale=(self.track_width, self.segment_length / 2),
            )
            glow = Entity(
                parent=entity,
                model="cube",
                scale=(self.track_width - 0.2, 0.1, self.segment_length - 0.2),
                color=emissive_color,
                y=0.3,
            )
            self.segments.append(TrackSegment(entity=entity, index=i))

    def _setup_ui(self) -> None:
        self.score_label = Text(
            text="Score: 0",
            origin=(0, 0),
            position=(-0.86, 0.45),
            scale=1.2,
            color=Color(0.8, 0.9, 1, 0.9),
        )
        self.high_score_label = Text(
            text="Best: 0",
            origin=(0, 0),
            position=(-0.86, 0.38),
            scale=1.0,
            color=Color(0.5, 0.75, 1, 0.7),
        )
        self.status_label = Text(
            text="Press SPACE to start",
            origin=(0, 0),
            position=(0, 0.1),
            scale=2.0,
            color=Color(1, 1, 1, 0.85),
        )
        self._default_status_color = self.status_label.color

    def _register_callbacks(self) -> None:
        self.app.update = self.update  # type: ignore[assignment]
        self.app.input = self.input  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Game lifecycle
    # ------------------------------------------------------------------
    def run(self) -> None:
        self.app.run()

    def start_run(self) -> None:
        self.is_running = True
        self.score = 0
        self.speed = 8.0
        self.vertical_velocity = 0.0
        self.player.position = Vec3(0, 1.1, -6)
        self.player.rotation = Vec3(0, 0, 0)
        for obstacle in self.obstacles:
            destroy(obstacle.entity)
        self.obstacles.clear()
        self.status_label.text = ""
        self.status_label.color = self._default_status_color
        self.player_hit_flash.enabled = False
        self.score_label.text = "Score: 0"
        self.high_score_label.text = f"Best: {int(self.high_score)}"
        if self.music:
            self.music.play()

    def end_run(self) -> None:
        if not self.is_running:
            return
        self.is_running = False
        self.high_score = max(self.high_score, self.score)
        self.status_label.text = "Crashed! Press R to retry"
        self.status_label.color = Color(1, 0.6, 0.6, 0.9)
        self.score_label.text = f"Score: {int(self.score)}"
        self.high_score_label.text = f"Best: {int(self.high_score)}"
        if self.crash_sound:
            self.crash_sound.play()
        if self.music:
            self.music.stop()
        self.player_hit_flash.enabled = True
        self.player_hit_flash.color = Color(1, 0.2, 0.2, 0.6)

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------
    def input(self, key: str) -> None:
        if key == "escape":
            self.app.user_exit()
        if key in {"space", "enter"} and not self.is_running:
            self.start_run()
            return
        if key == "r" and not self.is_running:
            self.start_run()
            return
        if not self.is_running:
            return
        if key == "space" and self._is_grounded():
            self.vertical_velocity = self.jump_force
            if self.jump_sound:
                self.jump_sound.play()

    # ------------------------------------------------------------------
    # Update loop
    # ------------------------------------------------------------------
    def update(self) -> None:
        dt = time.dt
        self.elapsed += dt
        if not self.is_running:
            self._idle_bobbing(dt)
            return

        self.speed = min(self.speed + self.acceleration * dt, self.max_speed)
        self._update_player_movement(dt)
        self._update_track_positions()
        self._update_obstacles()
        self._update_score(dt)

    def _idle_bobbing(self, dt: float) -> None:
        self.player.y = lerp(self.player.y, 1.1 + 0.2 * sin(self.elapsed * 2.0), dt * 4)

    def _update_player_movement(self, dt: float) -> None:
        direction = 0
        if held_keys["a"] or held_keys["left"]:
            direction -= 1
        if held_keys["d"] or held_keys["right"]:
            direction += 1

        target_lane = 0
        if direction < 0:
            target_lane = max(self.lanes[0], self.player.x - self.lateral_speed * dt)
        elif direction > 0:
            target_lane = min(self.lanes[-1], self.player.x + self.lateral_speed * dt)
        else:
            # Snap gently to the closest lane when there is no input.
            nearest_lane = min(self.lanes, key=lambda lane: abs(lane - self.player.x))
            target_lane = lerp(self.player.x, nearest_lane, dt * 4)

        self.player.x = lerp(self.player.x, target_lane, 0.7)
        self.player.z += self.speed * dt

        self.vertical_velocity -= self.gravity * dt
        self.player.y += self.vertical_velocity * dt

        if self._is_grounded():
            self.player.y = max(self.player.y, 1.1)
            if self.vertical_velocity < 0:
                self.vertical_velocity = 0

        if self.player.y < -5:
            self.end_run()

        self.camera_pivot.rotation_y = lerp(self.camera_pivot.rotation_y, direction * 12, dt * 6)

    def _update_track_positions(self) -> None:
        min_index = min(segment.index for segment in self.segments)
        max_index = max(segment.index for segment in self.segments)
        player_z = self.player.z
        for segment in self.segments:
            if segment.entity.z + self.segment_length < player_z - self.segment_length:
                segment.index = max_index + 1
                segment.entity.z = (max_index + 1) * self.segment_length
                max_index += 1
            elif segment.entity.z > player_z + self.segment_length * 6:
                segment.index = min_index - 1
                segment.entity.z = (min_index - 1) * self.segment_length
                min_index -= 1

    def _update_obstacles(self) -> None:
        player_z = self.player.z
        for obstacle in self.obstacles[:]:
            if obstacle.entity.z < player_z - 20:
                destroy(obstacle.entity)
                self.obstacles.remove(obstacle)
                continue
            if self.player.intersects(obstacle.entity).hit:
                self.end_run()

        self._spawn_obstacles()

    def _spawn_obstacles(self) -> None:
        player_z = self.player.z
        farthest_z = max([ob.entity.z for ob in self.obstacles], default=player_z)
        while farthest_z < player_z + self.segment_length * 4:
            farthest_z += random.uniform(12, 20)
            lane = random.choice(self.lanes)
            obstacle_entity = Entity(
                model="cube",
                scale=(2.6, random.uniform(2.5, 4.5), 2.6),
                color=Color(1, random.uniform(0.3, 0.7), random.uniform(0.3, 0.7), 1),
                collider="box",
                position=(lane, 1.25, farthest_z),
                texture="white_cube",
            )
            glow = Entity(
                parent=obstacle_entity,
                model="cube",
                scale=(1.1, 1.1, 1.1),
                color=Color(1, 0.5, 0.9, 0.3),
                y=obstacle_entity.scale_y * 0.5,
            )
            self.obstacles.append(Obstacle(entity=obstacle_entity, lane=lane))

    def _update_score(self, dt: float) -> None:
        self.score += self.speed * dt
        if self.score > self.high_score:
            self.high_score = self.score
        self.score_label.text = f"Score: {int(self.score)}"
        self.high_score_label.text = f"Best: {int(self.high_score)}"

    def _is_grounded(self) -> bool:
        start = self.player.world_position + Vec3(0, 0.6, 0)
        hit_info = raycast(start, Vec3(0, -1, 0), distance=0.8, ignore=(self.player,))
        return hit_info.hit


def main() -> None:
    """Launch the runner game."""

    game = RunnerGame()
    game.run()


if __name__ == "__main__":
    main()
