import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

/** Who may sign in. Each address is a separate account: the API scopes every
 * row by the signed-in email, so adding someone here gives them their own
 * empty profile, not a view of anyone else's. */
const ALLOWED_EMAILS = ["guanshunpeng@gmail.com", "peijinlee1224@gmail.com"];

/** The account the public /expo profile page shows. It has no session to
 * scope by, so the owner is named explicitly rather than inferred — otherwise
 * "first in the allowlist" would silently republish someone else's CV the day
 * that list is reordered. */
export const PUBLIC_PROFILE_USER =
  process.env.LOOM_PUBLIC_PROFILE_USER || "guanshunpeng@gmail.com";

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [Google],
  callbacks: {
    async signIn({ profile }) {
      return ALLOWED_EMAILS.includes(profile?.email ?? "");
    },
    async session({ session }) {
      return session;
    },
  },
  pages: {
    signIn: "/login",
    error: "/login",
  },
});
