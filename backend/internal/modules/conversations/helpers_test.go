package conversations

import (
	"time"

	"github.com/freshwood/builder-platform/backend/internal/platform/db"
)

func dbNow() time.Time { return db.Now() }
