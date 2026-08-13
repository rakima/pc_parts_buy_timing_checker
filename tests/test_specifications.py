import unittest

from victor.specifications import extract_specifications, format_specifications


class SpecificationsTest(unittest.TestCase):
    def test_extracts_gpu_model_and_vram(self) -> None:
        specs = extract_specifications("GPU", "GeForce RTX 5070 Ti 16GB GDDR7", "")
        self.assertEqual((('GPU', 'RTX 5070 TI'), ('VRAM', '16GB')), specs)

    def test_extracts_abbreviated_gpu_vram(self) -> None:
        specs = extract_specifications("GPU", "Radeon RX 9050 GAMING OC 8G GV-R9050", "")
        self.assertEqual((('GPU', 'RX 9050'), ('VRAM', '8GB')), specs)

    def test_extracts_cpu_model_socket_and_cooler(self) -> None:
        specs = extract_specifications(
            "CPU", "Ryzen 7 9800X3D", "Socket AM5対応 CPU ※CPUクーラー別売"
        )
        self.assertEqual((('CPU', 'Ryzen 7 9800X3D'), ('ソケット', 'AM5'),
                          ('クーラー', '別売')), specs)

    def test_extracts_ssd_capacity_form_and_interface(self) -> None:
        specs = extract_specifications(
            "SSD", "M.2 NVMe 内蔵SSD / 2TB / PCIe Gen4x4", ""
        )
        self.assertEqual((('容量', '2TB'), ('形状', 'M.2'), ('接続', 'PCIe Gen4x4')), specs)

    def test_extracts_memory_capacity_generation_speed_and_latency(self) -> None:
        specs = extract_specifications(
            "メモリ", "DDR5 SDRAM / 32GB（16GB×2） / DDR5-6000 CL36", ""
        )
        self.assertEqual((('容量', '32GB'), ('規格', 'DDR5'), ('速度', 'DDR5-6000'),
                          ('CL', '36')), specs)

    def test_formats_specs_for_ui(self) -> None:
        self.assertEqual("容量: 2TB / 形状: M.2", format_specifications(
            (("容量", "2TB"), ("形状", "M.2"))
        ))


if __name__ == "__main__":
    unittest.main()
