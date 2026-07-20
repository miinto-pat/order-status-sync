import unittest

from clients.ImpactSFTPClient import SFTPConfig, config_from_app_config


class ImpactSFTPClientTests(unittest.TestCase):
    def test_config_from_app_config_reads_nested_impact_sftp_settings(self):
        config = config_from_app_config(
            {
                "impact_sftp": {
                    "host": "ftp.example.com",
                    "port": "2222",
                    "username": "user",
                    "password": "secret",
                    "remote_dir": "/incoming",
                }
            }
        )

        self.assertEqual(
            config,
            SFTPConfig(
                host="ftp.example.com",
                port=2222,
                username="user",
                password="secret",
                remote_dir="/incoming",
            ),
        )

    def test_config_from_app_config_returns_none_when_required_values_are_missing(self):
        self.assertIsNone(config_from_app_config({"impact_sftp": {"host": "ftp.example.com"}}))


if __name__ == "__main__":
    unittest.main()
