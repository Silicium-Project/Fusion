import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description='Mock Raytracer')
    parser.add_argument('scene_path', help='Path to scene')
    parser.add_argument('--output', required=True, help='Output image path')
    parser.add_argument('--y-start', type=int)
    parser.add_argument('--y-end', type=int)
    parser.add_argument('--x-start', type=int)
    parser.add_argument('--x-end', type=int)
    args, unknown = parser.parse_known_args()

    # Create a 2x2 red image in PPM format
    ppm_data = b"P6\n2 2\n255\n"
    red_pixel = b"\xff\x00\x00"
    ppm_data += red_pixel * 4

    with open(args.output, "wb") as f:
        f.write(ppm_data)

    print(f"Mock rendering completed: {args.output}")

if __name__ == "__main__":
    main()
