//! Offline developer route planner using the runtime terrain/collision contract.
#[allow(dead_code)]
#[path = "../src/content.rs"]
mod content;
#[allow(dead_code)]
#[path = "../src/movement.rs"]
mod movement;
use serde_json::{Value, json};
use std::cmp::Reverse;
use std::collections::{BinaryHeap, HashMap};
use std::io::Read;

fn route() -> Result<Value, String> {
    let mut input = String::new();
    std::io::stdin()
        .take(4097)
        .read_to_string(&mut input)
        .map_err(|e| e.to_string())?;
    if input.len() > 4096 {
        return Err("Route request exceeds 4 KiB".into());
    }
    let input: Value = serde_json::from_str(&input).map_err(|e| e.to_string())?;
    let point = |key: &str| -> Result<(f32, f32), String> {
        let row = input[key]
            .as_array()
            .filter(|r| r.len() == 2)
            .ok_or("Expected two coordinates")?;
        let x = row[0].as_f64().ok_or("Invalid X")? as f32;
        let z = row[1].as_f64().ok_or("Invalid Z")? as f32;
        content::valid_spawn(x, z)?;
        Ok((x, z))
    };
    let start = point("start")?;
    let goal = point("goal")?;
    let position = |(x, z): (i32, i32)| (start.0 + x as f32 * 2.0, start.1 + z as f32 * 2.0);
    let heuristic = |p: (i32, i32)| {
        let (x, z) = position(p);
        ((x - goal.0).hypot(z - goal.1) * 5.0) as u32
    };
    let clear = |a: (f32, f32), b: (f32, f32)| content::clear_path(a.0, a.1, b.0, b.1, &[]);
    let mut queue = BinaryHeap::from([Reverse((heuristic((0, 0)), 0u32, (0, 0)))]);
    let mut cost = HashMap::from([((0, 0), 0u32)]);
    let mut parent = HashMap::new();
    let mut endpoint = None;
    while let Some(Reverse((_, g, p))) = queue.pop() {
        if cost.get(&p) != Some(&g) {
            continue;
        }
        let current = position(p);
        if (current.0 - goal.0).hypot(current.1 - goal.1) <= 3.0 && clear(current, goal) {
            endpoint = Some(p);
            break;
        }
        if cost.len() > 100_000 {
            return Err("Route search exceeds 100,000 cells".into());
        }
        for dx in -1i32..=1 {
            for dz in -1i32..=1 {
                if dx == 0 && dz == 0 {
                    continue;
                }
                let next = (p.0 + dx, p.1 + dz);
                let score = g + if dx == 0 || dz == 0 { 10 } else { 14 };
                if cost.get(&next).is_some_and(|old| *old <= score) {
                    continue;
                }
                let target = position(next);
                if content::valid_spawn(target.0, target.1).is_err() || !clear(current, target) {
                    continue;
                }
                cost.insert(next, score);
                parent.insert(next, p);
                queue.push(Reverse((score + heuristic(next), score, next)));
            }
        }
    }
    let mut p = endpoint.ok_or("No collision-clear route found")?;
    let mut points = vec![goal, position(p)];
    while p != (0, 0) {
        p = parent[&p];
        points.push(position(p));
    }
    points.reverse();
    let mut waypoints = vec![start];
    let mut cursor = 0;
    while cursor + 1 < points.len() {
        let mut next = cursor + 1;
        for candidate in cursor + 2..points.len() {
            let target = points[candidate];
            if (points[cursor].0 - target.0).hypot(points[cursor].1 - target.1) > 12.0 {
                break;
            }
            if clear(points[cursor], target) {
                next = candidate;
            }
        }
        waypoints.push(points[next]);
        cursor = next;
    }
    Ok(
        json!({"map_id":if content::YONGAN {"metin2_map_a1"}else{"training"},
        "map_hash":content::HASH.trim(),"grid_step_m":2,"max_segment_m":12,
        "visited_cells":cost.len(),"waypoints":waypoints,"authoritative_state":false}),
    )
}

fn main() {
    match route() {
        Ok(result) => println!("{result}"),
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(1);
        }
    }
}
