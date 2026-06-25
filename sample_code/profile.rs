//! Browser profile model.

use adcore::id::ProfileId;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// A browser profile with fingerprint and proxy configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Profile {
    /// Unique profile identifier.
    pub id: ProfileId,

    /// Profile name.
    pub name: String,

    /// Optional description.
    pub description: Option<String>,

    /// When the profile was created.
    pub created_at: DateTime<Utc>,

    /// When the profile was last modified.
    pub updated_at: DateTime<Utc>,

    /// Whether the profile is archived (soft delete).
    pub archived: bool,

    /// Fingerprint configuration for this profile.
    pub fingerprint: crate::FingerprintConfig,

    /// Proxy configuration for this profile.
    pub proxy: Option<crate::ProxyConfig>,
}

impl Profile {
    /// Create a new profile with the given name.
    #[must_use]
    pub fn new(name: impl Into<String>) -> Self {
        let now = Utc::now();
        Self {
            id: ProfileId::new(),
            name: name.into(),
            description: None,
            created_at: now,
            updated_at: now,
            archived: false,
            fingerprint: crate::FingerprintConfig::default(),
            proxy: None,
        }
    }

    /// Mark the profile as archived.
    pub fn archive(&mut self) {
        self.archived = true;
        self.updated_at = Utc::now();
    }

    /// Check if the profile is active (not archived).
    #[must_use]
    pub fn is_active(&self) -> bool {
        !self.archived
    }
}

#[cfg(test)]
mod tests {
    use super::Profile;

    #[test]
    fn test_new_profile_is_active() {
        let profile = Profile::new("test");
        assert!(profile.is_active());
    }

    #[test]
    fn test_archive_sets_flag() {
        let mut profile = Profile::new("test");
        profile.archive();
        assert!(profile.archived);
        assert!(!profile.is_active());
    }

    #[test]
    fn test_new_profile_has_name() {
        let profile = Profile::new("my profile");
        assert_eq!(profile.name, "my profile");
    }

    #[test]
    fn test_new_profile_no_description() {
        let profile = Profile::new("test");
        assert!(profile.description.is_none());
    }

    #[test]
    fn test_new_profile_not_archived() {
        let profile = Profile::new("test");
        assert!(!profile.archived);
    }

    #[test]
    fn test_new_profile_has_timestamps() {
        let profile = Profile::new("test");
        // created_at and updated_at are set to now
        assert!(profile.created_at <= chrono::Utc::now());
        assert!(profile.updated_at <= chrono::Utc::now());
    }

    #[test]
    fn test_new_profile_default_fingerprint() {
        let profile = Profile::new("test");
        // Default fingerprint has all axes disabled
        assert!(!profile.fingerprint.canvas.enabled);
        assert!(!profile.fingerprint.navigator.enabled);
    }

    #[test]
    fn test_new_profile_no_proxy() {
        let profile = Profile::new("test");
        assert!(profile.proxy.is_none());
    }

    #[test]
    fn test_archive_updates_timestamp() {
        let mut profile = Profile::new("test");
        let before = profile.updated_at;
        std::thread::sleep(std::time::Duration::from_millis(10));
        profile.archive();
        assert!(profile.updated_at >= before);
    }

    #[test]
    fn test_profile_clone() {
        let profile = Profile::new("test");
        let cloned = profile.clone();
        assert_eq!(profile.id, cloned.id);
        assert_eq!(profile.name, cloned.name);
    }

    #[test]
    fn test_profile_debug() {
        let profile = Profile::new("test");
        let debug_str = format!("{profile:?}");
        assert!(debug_str.contains("Profile"));
        assert!(debug_str.contains("test"));
    }
}
